from django.db import migrations

FORWARD = r"""
CREATE FUNCTION disputes_actor_allowed(p_user uuid, p_org uuid, p_roles text[])
RETURNS boolean LANGUAGE sql AS $$
    SELECT EXISTS (
        SELECT 1 FROM identity_user u
        JOIN identity_membership m ON m.user_id=u.id
        JOIN registry_organization o ON o.id=m.organization_id
        WHERE u.id=p_user AND o.id=p_org AND u.is_active AND u.is_demo
          AND o.is_active AND o.is_demo AND m.role=ANY(p_roles)
          AND split_part(m.role,'_',1)=o.kind AND m.revoked_at IS NULL
          AND m.starts_at<=clock_timestamp()
          AND (m.ends_at IS NULL OR m.ends_at>clock_timestamp())
    );
$$;

CREATE FUNCTION disputes_demo_claim(p_claim uuid) RETURNS boolean LANGUAGE sql AS $$
    SELECT EXISTS (
        SELECT 1 FROM complaints_reportedclaim q
        JOIN complaints_invoice i ON i.id=q.invoice_id
        JOIN complaints_submission s ON s.id=i.submission_id
        JOIN complaints_complaintimport b ON b.id=s.source_import_id
        JOIN policy_clearancecycle c ON c.id=b.cycle_id
        JOIN policy_policyversion p ON p.id=c.policy_id
        JOIN registry_organization ch ON ch.id=i.channel_id
        JOIN registry_organization a ON a.id=i.agency_id
        JOIN registry_client cl ON cl.id=i.client_id
        WHERE q.id=p_claim AND s.is_sealed AND b.is_sealed AND c.is_sealed
          AND s.is_demo AND b.is_demo AND p.is_demo AND p.status='candidate'
          AND ch.is_demo AND ch.kind='channel' AND a.is_demo AND a.kind='agency'
          AND cl.is_demo
    );
$$;

CREATE FUNCTION disputes_reject_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'Dispute and evidence history is immutable' USING ERRCODE='23001';
END;
$$;

CREATE FUNCTION disputes_guard_window() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NOT disputes_actor_allowed(NEW.created_by_id,NEW.organization_id,
                                  ARRAY['pba_policy_preparer']) OR NOT EXISTS (
        SELECT 1 FROM policy_clearancecycle c
        JOIN policy_policyversion p ON p.id=c.policy_id
        WHERE c.id=NEW.cycle_id AND c.is_sealed AND p.is_demo AND p.status='candidate'
    ) THEN
        RAISE EXCEPTION 'Response windows require a demo policy preparer and sealed cycle'
            USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION disputes_guard_draft() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE facts record;
BEGIN
    SELECT q.reported_due,i.agency_id,b.cycle_id INTO facts
    FROM complaints_reportedclaim q JOIN complaints_invoice i ON i.id=q.invoice_id
    JOIN complaints_submission s ON s.id=i.submission_id
    JOIN complaints_complaintimport b ON b.id=s.source_import_id WHERE q.id=NEW.claim_id;
    IF NOT disputes_demo_claim(NEW.claim_id) OR NEW.agency_id<>facts.agency_id
       OR NOT disputes_actor_allowed(NEW.created_by_id,NEW.agency_id,
                                    ARRAY['agency_preparer','agency_approver'])
       OR NEW.disputed_amount>facts.reported_due
       OR NEW.claim_snapshot->>'claim_id' IS DISTINCT FROM NEW.claim_id::text
       OR (NEW.claim_snapshot->>'reported_due')::numeric IS DISTINCT FROM facts.reported_due
       OR (NEW.window_id IS NOT NULL AND NOT EXISTS (
           SELECT 1 FROM disputes_sandboxresponsewindow w
           WHERE w.id=NEW.window_id AND w.cycle_id=facts.cycle_id
       )) THEN
        RAISE EXCEPTION 'Invalid fictional objection draft scope, amount or authority'
            USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION disputes_guard_case() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NOT disputes_demo_claim(NEW.claim_id)
       OR NOT disputes_actor_allowed(NEW.created_by_id,NEW.agency_id,
                                    ARRAY['agency_approver']) OR NOT EXISTS (
           SELECT 1 FROM complaints_reportedclaim q
           JOIN complaints_invoice i ON i.id=q.invoice_id
           WHERE q.id=NEW.claim_id AND i.agency_id=NEW.agency_id
             AND i.channel_id=NEW.channel_id
       ) THEN
        RAISE EXCEPTION 'A case requires its filed claim and current demo agency approver'
            USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION disputes_guard_revision() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE parent disputes_disputecase%ROWTYPE;
        prev disputes_disputerevision%ROWTYPE;
        d disputes_objectiondraft%ROWTYPE;
        w disputes_sandboxresponsewindow%ROWTYPE;
        facts record; expected_action text; minimum_simulation timestamptz;
BEGIN
    SELECT * INTO parent FROM disputes_disputecase WHERE id=NEW.case_id FOR UPDATE;
    SELECT * INTO prev FROM disputes_disputerevision
        WHERE case_id=NEW.case_id ORDER BY version DESC LIMIT 1;
    SELECT q.reported_due,s.simulation_at,b.cycle_id INTO facts
    FROM complaints_reportedclaim q JOIN complaints_invoice i ON i.id=q.invoice_id
    JOIN complaints_submission s ON s.id=i.submission_id
    JOIN complaints_complaintimport b ON b.id=s.source_import_id WHERE q.id=parent.claim_id;
    minimum_simulation=coalesce(prev.simulation_at,facts.simulation_at);
    IF parent.id IS NULL OR NOT disputes_demo_claim(parent.claim_id)
       OR NEW.agency_id<>parent.agency_id
       OR NOT disputes_actor_allowed(NEW.created_by_id,NEW.agency_id,
                                    ARRAY['agency_approver'])
       OR NEW.version<>coalesce(prev.version,0)+1
       OR NEW.simulation_at<minimum_simulation THEN
        RAISE EXCEPTION 'Revision requires current authority and the next case version'
            USING ERRCODE='23514';
    END IF;
    IF NEW.command_type='submit' THEN
        SELECT * INTO d FROM disputes_objectiondraft WHERE id=NEW.draft_id;
        SELECT * INTO w FROM disputes_sandboxresponsewindow WHERE id=d.window_id;
        expected_action=CASE WHEN prev.version IS NULL THEN 'raised'
            WHEN prev.action='withdrawn' THEN 'reopened' ELSE 'amended' END;
        IF d.id IS NULL OR d.claim_id<>parent.claim_id OR d.agency_id<>NEW.agency_id
           OR d.base_version<>coalesce(prev.version,0) OR w.id IS NULL
           OR w.cycle_id<>facts.cycle_id OR NEW.action<>expected_action
           OR NEW.disputed_amount<>d.disputed_amount
           OR NEW.disputed_amount>facts.reported_due
           OR NEW.simulation_at<w.opens_at OR NEW.simulation_at>=w.closes_at
           OR NEW.receipt->'claim' IS DISTINCT FROM d.claim_snapshot
           OR NEW.receipt->>'draft_id' IS DISTINCT FROM NEW.draft_id::text
           OR NEW.receipt->>'draft_hash' IS DISTINCT FROM d.content_hash THEN
            RAISE EXCEPTION 'Signed draft is stale, out of window or inconsistent'
                USING ERRCODE='23514';
        END IF;
    ELSIF NEW.command_type='withdraw' THEN
        IF prev.version IS NULL OR prev.action='withdrawn' OR NEW.action<>'withdrawn'
           OR NEW.disputed_amount<>0 OR NEW.draft_id IS NOT NULL THEN
            RAISE EXCEPTION 'Only an open objection may be withdrawn'
                USING ERRCODE='23514';
        END IF;
    ELSE
        RAISE EXCEPTION 'Unsupported dispute command' USING ERRCODE='23514';
    END IF;
    IF NEW.receipt->>'case_id' IS DISTINCT FROM NEW.case_id::text
       OR (NEW.receipt->>'version')::integer IS DISTINCT FROM NEW.version
       OR NEW.receipt->>'action' IS DISTINCT FROM NEW.action
       OR (NEW.receipt->>'disputed_amount')::numeric IS DISTINCT FROM NEW.disputed_amount
       OR NEW.receipt->>'previous_revision_id' IS DISTINCT FROM prev.id::text
       OR NEW.receipt->>'previous_revision_hash' IS DISTINCT FROM prev.content_hash
       OR NEW.receipt->>'financial_effect' IS DISTINCT FROM 'none'
       OR NEW.receipt->>'enforcement_effect' IS DISTINCT FROM 'none'
       OR NEW.receipt->'signer'->>'id' IS DISTINCT FROM NEW.created_by_id::text
       OR NEW.receipt->'signer'->>'organization_id' IS DISTINCT FROM NEW.agency_id::text
       OR (NEW.receipt->>'simulation_at')::timestamptz IS DISTINCT FROM NEW.simulation_at
       OR (NEW.receipt->>'actual_recorded_at')::timestamptz IS DISTINCT FROM NEW.created_at
       OR NEW.receipt->'claim'->>'claim_id' IS DISTINCT FROM parent.claim_id::text THEN
        RAISE EXCEPTION 'Revision receipt must match its signed record and predecessor'
            USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION disputes_guard_evidence() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE facts record; w disputes_sandboxresponsewindow%ROWTYPE; expected_timing text;
BEGIN
    SELECT i.channel_id,i.agency_id,s.simulation_at,b.cycle_id INTO facts
    FROM complaints_reportedclaim q JOIN complaints_invoice i ON i.id=q.invoice_id
    JOIN complaints_submission s ON s.id=i.submission_id
    JOIN complaints_complaintimport b ON b.id=s.source_import_id WHERE q.id=NEW.claim_id;
    SELECT * INTO w FROM disputes_sandboxresponsewindow WHERE id=NEW.window_id;
    expected_timing=CASE WHEN w.id IS NULL THEN 'window_unknown'
        WHEN NEW.simulation_at<w.opens_at THEN 'before_window'
        WHEN NEW.simulation_at>=w.closes_at THEN 'late' ELSE 'within_window' END;
    IF NOT disputes_demo_claim(NEW.claim_id)
       OR NEW.organization_id NOT IN (facts.channel_id,facts.agency_id)
       OR NOT disputes_actor_allowed(NEW.created_by_id,NEW.organization_id,
           ARRAY['agency_preparer','agency_approver','channel_preparer','channel_approver'])
       OR NEW.simulation_at<facts.simulation_at
       OR (w.id IS NOT NULL AND w.cycle_id<>facts.cycle_id)
       OR NEW.timing<>expected_timing
       OR NEW.receipt->>'statement' IS DISTINCT FROM NEW.statement
       OR NEW.receipt->>'source_reference' IS DISTINCT FROM NEW.source_reference
       OR NEW.receipt->>'timing' IS DISTINCT FROM NEW.timing
       OR NEW.receipt->>'verification_status' IS DISTINCT FROM 'unverified'
       OR NEW.receipt->>'financial_effect' IS DISTINCT FROM 'none'
       OR NEW.receipt->>'enforcement_effect' IS DISTINCT FROM 'none'
       OR NEW.receipt->'author'->>'id' IS DISTINCT FROM NEW.created_by_id::text
       OR NEW.receipt->'author'->>'organization_id' IS DISTINCT FROM NEW.organization_id::text
       OR NEW.receipt->'claim'->>'claim_id' IS DISTINCT FROM NEW.claim_id::text
       OR (NEW.receipt->>'simulation_at')::timestamptz IS DISTINCT FROM NEW.simulation_at
       OR (NEW.receipt->>'actual_recorded_at')::timestamptz IS DISTINCT FROM NEW.created_at THEN
        RAISE EXCEPTION 'Evidence requires its participant, current authority and matching receipt'
            USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END;
$$;
"""

TABLES = {
    "sandboxresponsewindow": "window",
    "objectiondraft": "draft",
    "disputecase": "case",
    "disputerevision": "revision",
    "claimevidence": "evidence",
}


class Migration(migrations.Migration):
    dependencies = [
        ("disputes", "0001_initial"),
        ("identity", "0003_remove_membership_membership_valid_role_and_more"),
        ("complaints", "0003_live_authority_guard"),
        ("policy", "0002_protect_snapshots"),
    ]
    operations = [
        migrations.RunSQL(
            sql=FORWARD
            + "\n".join(
                f"CREATE TRIGGER protect_{table} BEFORE UPDATE OR DELETE ON disputes_{table} "
                "FOR EACH ROW EXECUTE FUNCTION disputes_reject_mutation();\n"
                f"CREATE TRIGGER validate_{table} BEFORE INSERT ON disputes_{table} "
                f"FOR EACH ROW EXECUTE FUNCTION disputes_guard_{guard}();"
                for table, guard in TABLES.items()
            ),
            reverse_sql="\n".join(
                f"DROP TRIGGER protect_{table} ON disputes_{table};\n"
                f"DROP TRIGGER validate_{table} ON disputes_{table};\n"
                f"DROP FUNCTION disputes_guard_{guard}();"
                for table, guard in reversed(TABLES.items())
            )
            + "\nDROP FUNCTION disputes_reject_mutation();"
            "\nDROP FUNCTION disputes_demo_claim(uuid);"
            "\nDROP FUNCTION disputes_actor_allowed(uuid,uuid,text[]);",
        )
    ]
