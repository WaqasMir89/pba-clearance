from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("policy", "0001_initial")]
    operations = [
        migrations.RunSQL(
            sql="""
            CREATE FUNCTION clearance_reject_snapshot_mutation() RETURNS trigger
            LANGUAGE plpgsql AS $$
            BEGIN
                RAISE EXCEPTION 'Snapshots are immutable; create a new version'
                    USING ERRCODE = '23001';
            END;
            $$;
            CREATE TRIGGER clearance_policy_snapshot_immutable
                BEFORE UPDATE OR DELETE ON policy_policyversion
                FOR EACH ROW EXECUTE FUNCTION clearance_reject_snapshot_mutation();
            CREATE TRIGGER clearance_milestone_immutable
                BEFORE UPDATE OR DELETE ON policy_milestone
                FOR EACH ROW EXECUTE FUNCTION clearance_reject_snapshot_mutation();

            CREATE FUNCTION clearance_guard_cycle_snapshot() RETURNS trigger
            LANGUAGE plpgsql AS $$
            BEGIN
                IF TG_OP = 'UPDATE' THEN
                    IF NOT OLD.is_sealed AND NEW.is_sealed
                       AND (to_jsonb(OLD) - 'is_sealed') = (to_jsonb(NEW) - 'is_sealed') THEN
                        RETURN NEW;
                    END IF;
                END IF;
                RAISE EXCEPTION 'Cycle snapshots are immutable; create a new version'
                    USING ERRCODE = '23001';
            END;
            $$;
            CREATE TRIGGER clearance_cycle_immutable
                BEFORE UPDATE OR DELETE ON policy_clearancecycle
                FOR EACH ROW EXECUTE FUNCTION clearance_guard_cycle_snapshot();

            CREATE FUNCTION clearance_guard_milestone_insert() RETURNS trigger
            LANGUAGE plpgsql AS $$
            DECLARE sealed boolean;
            BEGIN
                SELECT is_sealed INTO sealed FROM policy_clearancecycle
                    WHERE id = NEW.cycle_id FOR UPDATE;
                IF sealed IS DISTINCT FROM FALSE THEN
                    RAISE EXCEPTION 'Cannot append to a sealed or missing cycle'
                        USING ERRCODE = '23001';
                END IF;
                RETURN NEW;
            END;
            $$;
            CREATE TRIGGER clearance_milestone_parent_guard
                BEFORE INSERT ON policy_milestone
                FOR EACH ROW EXECUTE FUNCTION clearance_guard_milestone_insert();
            ALTER TABLE policy_milestone ADD CONSTRAINT milestone_consistent_local_utc
                CHECK (occurs_at = ((local_date + local_time) AT TIME ZONE timezone_name));
            """,
            reverse_sql="""
            ALTER TABLE policy_milestone DROP CONSTRAINT milestone_consistent_local_utc;
            DROP TRIGGER clearance_milestone_parent_guard ON policy_milestone;
            DROP FUNCTION clearance_guard_milestone_insert();
            DROP TRIGGER clearance_cycle_immutable ON policy_clearancecycle;
            DROP FUNCTION clearance_guard_cycle_snapshot();
            DROP TRIGGER clearance_milestone_immutable ON policy_milestone;
            DROP TRIGGER clearance_policy_snapshot_immutable ON policy_policyversion;
            DROP FUNCTION clearance_reject_snapshot_mutation();
            """,
        )
    ]
