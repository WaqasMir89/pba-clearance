import hashlib
from datetime import UTC
from decimal import Decimal
from uuid import uuid4
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.audit.services import record_event
from apps.complaints.constants import DECLARATION_TEXT, DECLARATION_VERSION, VALIDATOR_VERSION
from apps.complaints.errors import AlreadyFiled, CommandConflict, FilingWindowClosed, PreviewChanged
from apps.complaints.models import ComplaintImport, ImportRow, Invoice, ReportedClaim, Submission
from apps.complaints.selectors import CHANNEL_ROLES, imports_for
from apps.complaints.validation import digest, money, parse_csv, validate_rows
from apps.identity.models import Membership, User
from apps.identity.selectors import workspace_membership
from apps.policy.models import ClearanceCycle
from apps.registry.models import Organization


def _channel_writer(actor, organization_id, *, filing=False):
    if settings.ENVIRONMENT != "development":
        raise PermissionDenied("Complaint filing is not enabled in this environment.")
    membership = workspace_membership(actor, organization_id, lock=True)
    if membership.role not in CHANNEL_ROLES or (
        filing and membership.role != Membership.Role.CHANNEL_APPROVER
    ):
        raise PermissionDenied(
            "A channel approver must file an import."
            if filing
            else "A channel member must stage an import."
        )
    # Serializes same-channel import/filing races; database uniqueness remains the final guard.
    channel = Organization.objects.select_for_update().get(pk=membership.organization_id)
    current_user = (
        User.objects.select_for_update().filter(pk=actor.pk, is_active=True, is_demo=True).first()
    )
    checked_at = timezone.now()
    if membership.starts_at > checked_at or (
        membership.ends_at is not None and membership.ends_at <= checked_at
    ):
        raise PermissionDenied("This workspace membership has expired or has not started.")
    if not channel.is_active or not channel.is_demo or current_user is None:
        raise PermissionDenied(
            "This intake is available only to active fictional sandbox accounts."
        )
    return membership, channel


def _candidate_cycle(cycle_id):
    cycle = get_object_or_404(
        ClearanceCycle.objects.select_related("policy").prefetch_related("milestones"),
        pk=cycle_id,
        is_sealed=True,
        policy__is_demo=True,
    )
    if cycle.policy.status != "candidate":
        raise PermissionDenied("Only a fictional candidate calendar is supported in this sandbox.")
    return cycle


@transaction.atomic
def stage_import(
    *,
    actor,
    organization_id,
    cycle_id,
    source_filename,
    source_bytes,
    idempotency_key,
    request_id=None,
):
    _, channel = _channel_writer(actor, organization_id)
    if (
        not source_filename.lower().endswith(".csv")
        or any(c in source_filename for c in ("/", "\\", "\x00", "\r", "\n"))
        or len(source_filename) > 120
    ):
        raise ValidationError(
            {"source_filename": "Use a CSV filename without a path, at most 120 characters."}
        )
    source_sha256 = hashlib.sha256(source_bytes).hexdigest()
    request_hash = digest(
        {
            "cycle_id": str(cycle_id),
            "source_filename": source_filename,
            "source_sha256": source_sha256,
            "validator_version": VALIDATOR_VERSION,
        }
    )
    previous = ComplaintImport.objects.filter(
        channel=channel, idempotency_key=idempotency_key
    ).first()
    if previous:
        if not previous.is_sealed:
            raise CommandConflict("The original import needs an authorized integrity review.")
        if previous.request_hash != request_hash:
            raise CommandConflict()
        return previous, True
    cycle = _candidate_cycle(cycle_id)
    source_rows = parse_csv(source_bytes)
    batch = ComplaintImport.objects.create(
        channel=channel,
        cycle=cycle,
        created_by=actor,
        source_filename=source_filename,
        source_bytes=source_bytes,
        source_sha256=source_sha256,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        row_count=len(source_rows),
        validator_version=VALIDATOR_VERSION,
    )
    rows = [ImportRow(batch=batch, **data) for data in source_rows]
    ImportRow.objects.bulk_create(rows)
    ComplaintImport.objects.filter(pk=batch.pk).update(is_sealed=True)
    batch.is_sealed = True
    record_event(
        actor=actor,
        organization_id=channel.pk,
        action="complaints.import_staged",
        subject=batch,
        details={"source_sha256": source_sha256, "row_count": len(rows), "sandbox": True},
        request_id=request_id,
    )
    return batch, False


def preview_import(batch):
    if batch.validator_version != VALIDATOR_VERSION:
        raise ValidationError({"import": "This import requires its original validation version."})
    rows = validate_rows(list(batch.rows.all()), channel=batch.channel, cycle=batch.cycle)
    counts = {
        status: sum(row["status"] == status for row in rows)
        for status in ("ready", "invalid", "review", "duplicate")
    }
    total = sum(
        (Decimal(row["canonical"]["reported_due"]) for row in rows if row["status"] == "ready"),
        Decimal("0.00"),
    )
    context = {
        "import_id": str(batch.pk),
        "channel_id": str(batch.channel_id),
        "cycle_id": str(batch.cycle_id),
        "policy_id": str(batch.cycle.policy_id),
        "source_sha256": batch.source_sha256,
        "validator_version": batch.validator_version,
        "rows": rows,
    }
    return {
        "rows": rows,
        "counts": counts,
        "ready_reported_total": money(total),
        "preview_hash": digest(context),
        "checked_at": timezone.now(),
    }


def import_detail(batch):
    submission = Submission.objects.filter(source_import=batch, is_sealed=True).first()
    return {
        "id": batch.pk,
        "channel_id": batch.channel_id,
        "cycle_id": batch.cycle_id,
        "cycle_code": batch.cycle.code,
        "source_filename": batch.source_filename,
        "source_sha256": batch.source_sha256,
        "created_at": batch.created_at,
        "created_by": batch.created_by.username,
        "row_count": batch.row_count,
        "validator_version": batch.validator_version,
        "is_demo": True,
        "submission_id": submission.pk if submission else None,
        "preview": submission.preview_snapshot if submission else preview_import(batch),
        "preview_current": submission is None,
    }


def _filing_clock(cycle, simulation_at, ready):
    if timezone.is_naive(simulation_at):
        raise ValidationError({"simulation_at": "Provide an explicit timezone offset."})
    milestones = {milestone.code: milestone.occurs_at for milestone in cycle.milestones.all()}
    opening, closing = milestones.get("complaint_open"), milestones.get("complaint_close")
    if opening is None or closing is None:
        raise ValidationError({"cycle": "This candidate calendar has no complete filing window."})
    if not opening <= simulation_at < closing:
        raise FilingWindowClosed()
    local_date = simulation_at.astimezone(ZoneInfo("Asia/Karachi")).date().isoformat()
    future_rows = [
        row["number"]
        for row in ready
        if row["canonical"]["invoice_date"] > local_date
        or (
            row["canonical"]["invoice_delivered_on"]
            and row["canonical"]["invoice_delivered_on"] > local_date
        )
    ]
    if future_rows:
        raise ValidationError(
            {"simulation_at": "The simulation precedes ready invoice/delivery dates."}
        )
    return opening, closing


@transaction.atomic
def file_import(
    *,
    actor,
    organization_id,
    import_id,
    expected_preview_hash,
    simulation_at,
    declaration_version,
    declaration_accepted,
    idempotency_key,
    request_id=None,
):
    membership, channel = _channel_writer(actor, organization_id, filing=True)
    batch = get_object_or_404(
        imports_for(membership)
        .select_related("cycle__policy", "channel", "created_by")
        .prefetch_related("rows", "cycle__milestones"),
        pk=import_id,
    )
    if timezone.is_naive(simulation_at):
        raise ValidationError({"simulation_at": "Provide an explicit timezone offset."})
    simulation_at = simulation_at.astimezone(UTC)
    request_hash = digest(
        {
            "import_id": str(batch.pk),
            "expected_preview_hash": expected_preview_hash,
            "simulation_at": simulation_at.isoformat(),
            "declaration_version": declaration_version,
            "declaration_accepted": declaration_accepted,
        }
    )
    previous = Submission.objects.filter(channel=channel, idempotency_key=idempotency_key).first()
    if previous:
        if not previous.is_sealed:
            raise CommandConflict("The original filing needs an authorized integrity review.")
        if previous.request_hash != request_hash:
            raise CommandConflict()
        return previous, True
    if Submission.objects.filter(source_import=batch).exists():
        raise AlreadyFiled()
    if declaration_version != DECLARATION_VERSION or declaration_accepted is not True:
        raise ValidationError(
            {"declaration": "Accept the current fictional-report declaration before filing."}
        )
    _candidate_cycle(batch.cycle_id)
    preview = preview_import(batch)
    if preview["preview_hash"] != expected_preview_hash:
        raise PreviewChanged()
    ready = [row for row in preview["rows"] if row["status"] == "ready"]
    if not ready:
        raise ValidationError(
            {"import": "There are no ready rows to file. Correct or review the source."}
        )
    opening, closing = _filing_clock(batch.cycle, simulation_at, ready)
    submitted_at, submission_id = timezone.now(), uuid4()
    invoice_ids = {row["id"]: uuid4() for row in ready}
    claim_ids = {row["id"]: uuid4() for row in ready}
    receipt = {
        "schema": "sandbox-complaint-receipt-v1",
        "id": str(submission_id),
        "is_demo": True,
        "submitted_at": submitted_at.isoformat(),
        "simulation_at": simulation_at.isoformat(),
        "signer": {"id": str(actor.pk), "username": actor.username, "role": membership.role},
        "channel": {"id": str(channel.pk), "code": channel.code, "legal_name": channel.legal_name},
        "source": {
            "import_id": str(batch.pk),
            "filename": batch.source_filename,
            "sha256": batch.source_sha256,
        },
        "cycle": {
            "id": str(batch.cycle_id),
            "code": batch.cycle.code,
            "broadcast_start": batch.cycle.broadcast_start.isoformat(),
            "broadcast_end": batch.cycle.broadcast_end.isoformat(),
            "filing_opens_at": opening.isoformat(),
            "filing_closes_at": closing.isoformat(),
        },
        "policy": {
            "id": str(batch.cycle.policy_id),
            "code": batch.cycle.policy.code,
            "version": batch.cycle.policy.version,
            "source_reference": batch.cycle.policy.source_reference,
            "source_sha256": batch.cycle.policy.source_sha256,
            "status": "candidate",
        },
        "declaration": {"version": DECLARATION_VERSION, "text": DECLARATION_TEXT},
        "validator_version": batch.validator_version,
        "preview_hash": expected_preview_hash,
        "row_count": len(ready),
        "reported_total": preview["ready_reported_total"],
        "currency": "PKR",
        "rows": [
            dict(
                row["canonical"],
                source_row_id=row["id"],
                source_row_number=row["number"],
                invoice_id=str(invoice_ids[row["id"]]),
                claim_id=str(claim_ids[row["id"]]),
            )
            for row in ready
        ],
        "excluded_rows": [
            {"number": row["number"], "status": row["status"]}
            for row in preview["rows"]
            if row["status"] != "ready"
        ],
    }
    try:
        with transaction.atomic():
            submission = Submission.objects.create(
                id=submission_id,
                source_import=batch,
                channel=channel,
                submitted_by=actor,
                submitted_at=submitted_at,
                simulation_at=simulation_at,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                content_hash=digest(receipt),
                receipt=receipt,
                preview_snapshot={**preview, "checked_at": preview["checked_at"].isoformat()},
                row_count=len(ready),
                reported_total=preview["ready_reported_total"],
            )
            invoices, claims = [], []
            for row in ready:
                facts = row["canonical"]
                invoices.append(
                    Invoice(
                        id=invoice_ids[row["id"]],
                        submission=submission,
                        source_row_id=row["id"],
                        channel=channel,
                        agency_id=facts["agency_id"],
                        client_id=facts["client_id"],
                        financial_year=facts["financial_year"],
                        invoice_number=facts["invoice_number"],
                        normalized_number=facts["normalized_number"],
                        comparison_key=facts["comparison_key"],
                        invoice_date=facts["invoice_date"],
                        broadcast_start=facts["broadcast_start"],
                        broadcast_end=facts["broadcast_end"],
                        principal_amount=facts["principal_amount"],
                        gst_amount=facts["gst_amount"],
                        invoice_total=facts["invoice_total"],
                        currency="PKR",
                        delivery_reference=facts["delivery_reference"],
                        invoice_delivered_on=facts["invoice_delivered_on"],
                        release_order_reference=facts["release_order_reference"],
                        source_id=facts["source_id"],
                        report_fingerprint=facts["fingerprint"],
                    )
                )
                claims.append(
                    ReportedClaim(
                        id=claim_ids[row["id"]],
                        invoice_id=invoice_ids[row["id"]],
                        reported_due=facts["reported_due"],
                        balance_explanation=facts["balance_explanation"],
                    )
                )
            Invoice.objects.bulk_create(invoices)
            ReportedClaim.objects.bulk_create(claims)
            Submission.objects.filter(pk=submission.pk).update(is_sealed=True)
            submission.is_sealed = True
    except IntegrityError as exc:
        raise PreviewChanged() from exc
    record_event(
        actor=actor,
        organization_id=channel.pk,
        action="complaints.submitted",
        subject=submission,
        details={
            "content_hash": submission.content_hash,
            "row_count": len(ready),
            "reported_total": preview["ready_reported_total"],
            "sandbox": True,
        },
        request_id=request_id,
    )
    return submission, False
