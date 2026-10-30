from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("complaints", "0002_protect_filing")]
    operations = [
        migrations.RunSQL(
            sql="""
        CREATE OR REPLACE FUNCTION complaints_guard_submission() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE invoice_count bigint; claim_count bigint; due_total numeric;
        BEGIN
            IF TG_OP = 'INSERT' THEN
                IF NEW.is_sealed OR NOT EXISTS (
                    SELECT 1 FROM complaints_complaintimport b
                    JOIN registry_organization o ON o.id=b.channel_id,
                        identity_user u JOIN identity_membership m ON m.user_id=u.id
                    WHERE b.id=NEW.source_import_id AND b.is_sealed AND b.channel_id=NEW.channel_id
                      AND o.kind='channel' AND o.is_demo AND o.is_active
                      AND u.id=NEW.submitted_by_id AND u.is_demo AND u.is_active
                      AND m.organization_id=NEW.channel_id AND m.role='channel_approver'
                      AND m.revoked_at IS NULL AND m.starts_at<=clock_timestamp()
                      AND (m.ends_at IS NULL OR m.ends_at>clock_timestamp())
                ) THEN
                    RAISE EXCEPTION 'Filing requires a current sandbox channel and approver'
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
        """,
            reverse_sql="""
        CREATE OR REPLACE FUNCTION complaints_guard_submission() RETURNS trigger
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
        """,
        )
    ]
