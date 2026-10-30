from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("complaints", "0001_initial")]
    operations = [
        migrations.RunSQL(
            sql="""
            CREATE FUNCTION complaints_reject_mutation() RETURNS trigger
            LANGUAGE plpgsql AS $$
            BEGIN
                RAISE EXCEPTION 'Complaint history is immutable; create an authorized correction'
                    USING ERRCODE = '23001';
            END;
            $$;
            CREATE TRIGGER complaints_row_immutable BEFORE UPDATE OR DELETE ON complaints_importrow
                FOR EACH ROW EXECUTE FUNCTION complaints_reject_mutation();
            CREATE TRIGGER complaints_invoice_immutable BEFORE UPDATE OR DELETE ON complaints_invoice
                FOR EACH ROW EXECUTE FUNCTION complaints_reject_mutation();
            CREATE TRIGGER complaints_claim_immutable BEFORE UPDATE OR DELETE ON complaints_reportedclaim
                FOR EACH ROW EXECUTE FUNCTION complaints_reject_mutation();

            CREATE FUNCTION complaints_guard_import() RETURNS trigger
            LANGUAGE plpgsql AS $$
            DECLARE rows_count bigint;
            BEGIN
                IF TG_OP = 'INSERT' THEN
                    IF NEW.is_sealed OR NOT EXISTS (
                        SELECT 1 FROM registry_organization o, identity_user u,
                            policy_clearancecycle c JOIN policy_policyversion p ON p.id=c.policy_id
                        WHERE o.id=NEW.channel_id AND o.kind='channel' AND o.is_demo AND o.is_active
                          AND u.id=NEW.created_by_id AND u.is_demo AND u.is_active
                          AND c.id=NEW.cycle_id AND c.is_sealed AND p.is_demo AND p.status='candidate'
                    ) THEN
                        RAISE EXCEPTION 'Import requires a fictional channel, user and candidate cycle'
                            USING ERRCODE = '23514';
                    END IF;
                    RETURN NEW;
                ELSIF TG_OP = 'UPDATE' THEN
                    IF NOT OLD.is_sealed AND NEW.is_sealed
                       AND (to_jsonb(OLD)-'is_sealed')=(to_jsonb(NEW)-'is_sealed') THEN
                        SELECT count(*) INTO rows_count FROM complaints_importrow WHERE batch_id=OLD.id;
                        IF rows_count=OLD.row_count THEN RETURN NEW; END IF;
                    END IF;
                END IF;
                RAISE EXCEPTION 'Import snapshots cannot be changed or incorrectly sealed'
                    USING ERRCODE = '23001';
            END;
            $$;
            CREATE TRIGGER complaints_import_guard BEFORE INSERT OR UPDATE OR DELETE ON complaints_complaintimport
                FOR EACH ROW EXECUTE FUNCTION complaints_guard_import();

            CREATE FUNCTION complaints_guard_import_row() RETURNS trigger
            LANGUAGE plpgsql AS $$
            DECLARE sealed boolean;
            BEGIN
                SELECT is_sealed INTO sealed FROM complaints_complaintimport
                    WHERE id=NEW.batch_id FOR UPDATE;
                IF sealed IS DISTINCT FROM FALSE THEN
                    RAISE EXCEPTION 'Cannot append to a sealed or missing import'
                        USING ERRCODE = '23001';
                END IF;
                RETURN NEW;
            END;
            $$;
            CREATE TRIGGER complaints_import_row_parent BEFORE INSERT ON complaints_importrow
                FOR EACH ROW EXECUTE FUNCTION complaints_guard_import_row();

            CREATE FUNCTION complaints_guard_submission() RETURNS trigger
            LANGUAGE plpgsql AS $$
            DECLARE invoice_count bigint; claim_count bigint; due_total numeric;
            BEGIN
                IF TG_OP = 'INSERT' THEN
                    IF NEW.is_sealed OR NOT EXISTS (
                        SELECT 1 FROM complaints_complaintimport b, identity_user u
                        JOIN identity_membership m ON m.user_id=u.id
                        WHERE b.id=NEW.source_import_id AND b.is_sealed AND b.channel_id=NEW.channel_id
                          AND u.id=NEW.submitted_by_id AND u.is_demo AND u.is_active
                          AND m.organization_id=NEW.channel_id AND m.role='channel_approver'
                          AND m.revoked_at IS NULL AND m.starts_at<=CURRENT_TIMESTAMP
                          AND (m.ends_at IS NULL OR m.ends_at>CURRENT_TIMESTAMP)
                    ) THEN
                        RAISE EXCEPTION 'Filing requires a sealed import and current fictional channel approver'
                            USING ERRCODE = '23514';
                    END IF;
                    RETURN NEW;
                ELSIF TG_OP = 'UPDATE' THEN
                    IF NOT OLD.is_sealed AND NEW.is_sealed
                       AND (to_jsonb(OLD)-'is_sealed')=(to_jsonb(NEW)-'is_sealed') THEN
                        SELECT count(i.id),count(c.id),coalesce(sum(c.reported_due),0)
                            INTO invoice_count,claim_count,due_total FROM complaints_invoice i
                            LEFT JOIN complaints_reportedclaim c ON c.invoice_id=i.id
                            WHERE i.submission_id=OLD.id;
                        IF invoice_count=OLD.row_count AND claim_count=OLD.row_count
                           AND due_total=OLD.reported_total
                           AND (OLD.receipt->>'row_count')::integer=OLD.row_count
                           AND (OLD.receipt->>'reported_total')::numeric=OLD.reported_total
                           AND OLD.preview_snapshot->>'preview_hash'=OLD.receipt->>'preview_hash' THEN
                            RETURN NEW;
                        END IF;
                    END IF;
                END IF;
                RAISE EXCEPTION 'Filing snapshots cannot be changed or sealed with inconsistent totals'
                    USING ERRCODE = '23001';
            END;
            $$;
            CREATE TRIGGER complaints_submission_guard BEFORE INSERT OR UPDATE OR DELETE ON complaints_submission
                FOR EACH ROW EXECUTE FUNCTION complaints_guard_submission();

            CREATE FUNCTION complaints_guard_invoice() RETURNS trigger
            LANGUAGE plpgsql AS $$
            DECLARE sealed boolean; original_batch uuid; original_channel uuid;
            BEGIN
                SELECT is_sealed,source_import_id,channel_id INTO sealed,original_batch,original_channel
                    FROM complaints_submission WHERE id=NEW.submission_id FOR UPDATE;
                IF sealed IS DISTINCT FROM FALSE OR original_channel<>NEW.channel_id OR NOT EXISTS (
                    SELECT 1 FROM complaints_importrow r, registry_organization a,
                        registry_client c WHERE r.id=NEW.source_row_id AND r.batch_id=original_batch
                        AND a.id=NEW.agency_id AND a.kind='agency' AND a.is_demo AND a.is_active
                        AND c.id=NEW.client_id AND c.is_demo
                ) THEN
                    RAISE EXCEPTION 'Invoice must belong to its unsealed sandbox filing and original source'
                        USING ERRCODE = '23514';
                END IF;
                RETURN NEW;
            END;
            $$;
            CREATE TRIGGER complaints_invoice_parent BEFORE INSERT ON complaints_invoice
                FOR EACH ROW EXECUTE FUNCTION complaints_guard_invoice();

            CREATE FUNCTION complaints_guard_claim() RETURNS trigger
            LANGUAGE plpgsql AS $$
            DECLARE sealed boolean; total numeric;
            BEGIN
                SELECT s.is_sealed,i.invoice_total INTO sealed,total FROM complaints_invoice i
                    JOIN complaints_submission s ON s.id=i.submission_id
                    WHERE i.id=NEW.invoice_id FOR UPDATE OF s;
                IF sealed IS DISTINCT FROM FALSE OR NEW.reported_due>total THEN
                    RAISE EXCEPTION 'Claim must fit its invoice and belong to an unsealed filing'
                        USING ERRCODE = '23514';
                END IF;
                RETURN NEW;
            END;
            $$;
            CREATE TRIGGER complaints_claim_parent BEFORE INSERT ON complaints_reportedclaim
                FOR EACH ROW EXECUTE FUNCTION complaints_guard_claim();
            ALTER TABLE complaints_complaintimport ADD CONSTRAINT import_bounded_source
                CHECK (octet_length(source_bytes)>0 AND octet_length(source_bytes)<=262144);
            ALTER TABLE complaints_complaintimport ADD CONSTRAINT import_verified_source_hash
                CHECK (source_sha256=encode(sha256(source_bytes),'hex'));
            """,
            reverse_sql="""
            ALTER TABLE complaints_complaintimport DROP CONSTRAINT import_verified_source_hash;
            ALTER TABLE complaints_complaintimport DROP CONSTRAINT import_bounded_source;
            DROP TRIGGER complaints_claim_parent ON complaints_reportedclaim;
            DROP FUNCTION complaints_guard_claim();
            DROP TRIGGER complaints_invoice_parent ON complaints_invoice;
            DROP FUNCTION complaints_guard_invoice();
            DROP TRIGGER complaints_submission_guard ON complaints_submission;
            DROP FUNCTION complaints_guard_submission();
            DROP TRIGGER complaints_import_row_parent ON complaints_importrow;
            DROP FUNCTION complaints_guard_import_row();
            DROP TRIGGER complaints_import_guard ON complaints_complaintimport;
            DROP FUNCTION complaints_guard_import();
            DROP TRIGGER complaints_claim_immutable ON complaints_reportedclaim;
            DROP TRIGGER complaints_invoice_immutable ON complaints_invoice;
            DROP TRIGGER complaints_row_immutable ON complaints_importrow;
            DROP FUNCTION complaints_reject_mutation();
            """,
        )
    ]
