import csv
import io
from datetime import UTC, date, datetime, time
from uuid import uuid4

from apps.complaints.constants import DECLARATION_VERSION, HEADERS
from apps.complaints.services import file_import, preview_import, stage_import
from apps.identity.models import Membership, User
from apps.policy.services import create_candidate_cycle, create_candidate_policy
from apps.registry.models import Client, ClientAccess, Organization


def prepare_intake(workspace):
    Organization.objects.all().update(is_demo=True)
    Client.objects.all().update(is_demo=True)
    User.objects.all().update(is_demo=True)
    workspace.maker = User.objects.create_user(username="fictional-maker", is_demo=True)
    workspace.checker = User.objects.create_user(username="fictional-checker", is_demo=True)
    workspace.other_checker = User.objects.create_user(
        username="fictional-other-checker", is_demo=True
    )
    workspace.policy_actor = User.objects.create_user(username="fictional-policy", is_demo=True)
    workspace.other_channel = Organization.objects.create(
        code="another-channel", legal_name="Another Fictional Channel", kind="channel", is_demo=True
    )
    for user, organization, role in [
        (workspace.maker, workspace.channel, "channel_preparer"),
        (workspace.checker, workspace.channel, "channel_approver"),
        (workspace.other_checker, workspace.other_channel, "channel_approver"),
        (workspace.policy_actor, workspace.pba, "pba_policy_preparer"),
    ]:
        Membership.objects.create(user=user, organization=organization, role=role)
    for client, organization in [
        (workspace.client, workspace.channel),
        (workspace.foreign_client, workspace.channel),
        (workspace.client, workspace.other_channel),
    ]:
        ClientAccess.objects.get_or_create(client=client, organization=organization)
    policy = create_candidate_policy(
        actor=workspace.policy_actor,
        organization_id=workspace.pba.id,
        code="fictional-policy",
        version=1,
        title="Fictional Policy",
        source_reference="fictional source",
        source_sha256="a" * 64,
        effective_from=date(2026, 1, 1),
        effective_until=date(2027, 1, 1),
    )
    workspace.cycle = create_candidate_cycle(
        actor=workspace.policy_actor,
        organization_id=workspace.pba.id,
        policy_id=policy.id,
        code="fictional-cycle",
        title="Fictional cycle",
        broadcast_start=date(2026, 7, 1),
        broadcast_end=date(2026, 7, 31),
        milestones=[
            {"code": "complaint_open", "local_date": date(2026, 10, 5), "local_time": time(9)},
            {"code": "complaint_close", "local_date": date(2026, 10, 9), "local_time": time(17)},
            {"code": "payment_cutoff", "local_date": date(2026, 10, 19), "local_time": time(17)},
        ],
    )
    return workspace


def row(**changes):
    values = {
        "agency_code": "sample-agency",
        "client_code": "sample-client",
        "financial_year": "2026-2027",
        "invoice_number": "INV/001",
        "invoice_date": "2026-08-05",
        "broadcast_start": "2026-07-01",
        "broadcast_end": "2026-07-31",
        "principal_amount": "1000.00",
        "gst_amount": "180.00",
        "invoice_total": "1180.00",
        "reported_due": "1180.00",
        "currency": "PKR",
        "delivery_reference": "fictional acknowledgement",
        "invoice_delivered_on": "2026-08-06",
        "release_order_reference": "fictional release",
        "source_id": "source-001",
        "balance_explanation": "",
    }
    return {**values, **changes}


def source_csv(rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=HEADERS)
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def stage(context, rows=None, **changes):
    values = {
        "actor": context.maker,
        "organization_id": context.channel.id,
        "cycle_id": context.cycle.id,
        "source_filename": "fictional.csv",
        "source_bytes": source_csv(rows or [row()]),
        "idempotency_key": uuid4(),
    }
    return stage_import(**{**values, **changes})


def filing_args(context, batch, **changes):
    values = {
        "actor": context.checker,
        "organization_id": context.channel.id,
        "import_id": batch.id,
        "expected_preview_hash": preview_import(batch)["preview_hash"],
        "simulation_at": datetime(2026, 10, 6, 7, tzinfo=UTC),
        "declaration_version": DECLARATION_VERSION,
        "declaration_accepted": True,
        "idempotency_key": uuid4(),
    }
    return {**values, **changes}


def file(context, batch, **changes):
    return file_import(**filing_args(context, batch, **changes))
