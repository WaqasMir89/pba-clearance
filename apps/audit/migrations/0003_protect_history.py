from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("audit", "0002_initial")]
    operations = [
        migrations.RunSQL(
            sql="""
                CREATE FUNCTION clearance_reject_audit_mutation() RETURNS trigger
                LANGUAGE plpgsql AS $$
                BEGIN
                    RAISE EXCEPTION 'Audit history is append-only; use linked corrections'
                        USING ERRCODE = '23001';
                END;
                $$;
                CREATE TRIGGER clearance_audit_immutable
                BEFORE UPDATE OR DELETE ON audit_auditevent
                FOR EACH ROW EXECUTE FUNCTION clearance_reject_audit_mutation();
            """,
            reverse_sql="""
                DROP TRIGGER clearance_audit_immutable ON audit_auditevent;
                DROP FUNCTION clearance_reject_audit_mutation();
            """,
        )
    ]
