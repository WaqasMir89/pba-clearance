from decimal import Decimal
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.audit.services import record_event
from apps.complaints.errors import CommandConflict
from apps.complaints.selectors import AGENCY_ROLES, CHANNEL_ROLES, claims_for
from apps.complaints.validation import digest, money
from apps.disputes import validation
from apps.disputes.constants import DECLARATIONS, REASONS
from apps.disputes.errors import PreviewConflict, ResponseWindowClosed, VersionConflict
from apps.disputes.models import (
    ClaimEvidence,
    DisputeCase,
    DisputeRevision,
    ObjectionDraft,
    SandboxResponseWindow,
)
from apps.disputes.selectors import drafts_for
from apps.identity.models import Membership, User
from apps.identity.selectors import workspace_membership
from apps.policy.models import ClearanceCycle
from apps.registry.models import Organization


def writer(actor, organization_id, roles):
    if settings.ENVIRONMENT != "development":
        raise PermissionDenied(
            "Objection/evidence mutations are enabled only in the development sandbox."
        )
    membership = workspace_membership(actor, organization_id, lock=True)
    if membership.role not in roles:
        raise PermissionDenied("This role cannot perform the requested objection/evidence command.")
    organization = Organization.objects.select_for_update().get(pk=membership.organization_id)
    user = (
        User.objects.select_for_update().filter(pk=actor.pk, is_demo=True, is_active=True).first()
    )
    now = timezone.now()
    if (
        not organization.is_demo
        or not organization.is_active
        or user is None
        or membership.starts_at > now
        or (membership.ends_at and membership.ends_at <= now)
    ):
        raise PermissionDenied("A current fictional user and organization membership are required.")
    return membership


def claim_for_writer(membership, claim_id):
    claim = get_object_or_404(
        claims_for(membership)
        .select_for_update(of=("self",))
        .select_related(
            "invoice__channel",
            "invoice__agency",
            "invoice__client",
            "invoice__submission__source_import__cycle__policy",
        ),
        pk=claim_id,
    )
    invoice = claim.invoice
    if not (
        invoice.channel.is_demo
        and invoice.agency.is_demo
        and invoice.client.is_demo
        and invoice.submission.is_demo
        and invoice.submission.source_import.cycle.policy.is_demo
    ):
        raise PermissionDenied("Only explicitly fictional filed claims support sandbox commands.")
    return claim


def version(value):
    if type(value) is not int or not 0 <= value <= 2147483646:
        raise ValidationError({"expected_case_version": "Use a nonnegative current case version."})
    return value


def latest_revision(claim_id):
    return DisputeRevision.objects.filter(case__claim_id=claim_id).order_by("-version").first()


def claim_snapshot(claim):
    invoice = claim.invoice
    submission = invoice.submission
    original = next(row for row in submission.receipt["rows"] if row["claim_id"] == str(claim.pk))
    return {
        "claim_id": str(claim.pk),
        "invoice_id": str(invoice.pk),
        "invoice_number": invoice.invoice_number,
        "financial_year": invoice.financial_year,
        "channel_id": str(invoice.channel_id),
        "channel_name": submission.receipt["channel"]["legal_name"],
        "agency_id": str(invoice.agency_id),
        "agency_name": original["agency_name"],
        "client_id": str(invoice.client_id),
        "client_name": original["client_name"],
        "reported_due": money(claim.reported_due),
        "currency": "PKR",
        "cycle_id": str(submission.source_import.cycle_id),
        "cycle_code": submission.source_import.cycle.code,
        "source_submission_id": str(submission.pk),
        "source_submission_hash": submission.content_hash,
    }


def replay(model, request_hash, **lookup):
    previous = model.objects.filter(**lookup).first()
    if previous and previous.request_hash != request_hash:
        raise CommandConflict()
    return previous


@transaction.atomic
def create_window(
    *,
    actor,
    organization_id,
    cycle_id,
    opens_at,
    closes_at,
    source_reference,
    source_sha256,
    idempotency_key,
    request_id=None,
):
    writer(actor, organization_id, {Membership.Role.PBA_POLICY_PREPARER})
    opens_at, closes_at = (
        validation.instant(opens_at, "opens_at"),
        validation.instant(closes_at, "closes_at"),
    )
    source_reference = validation.text(source_reference, "source_reference", limit=255)
    payload = {
        "cycle_id": str(cycle_id),
        "opens_at": opens_at.isoformat(),
        "closes_at": closes_at.isoformat(),
        "source_reference": source_reference,
        "source_sha256": source_sha256,
    }
    request_hash = digest(payload)
    previous = replay(
        SandboxResponseWindow,
        request_hash,
        organization_id=organization_id,
        idempotency_key=idempotency_key,
    )
    if previous:
        return previous, True
    cycle = get_object_or_404(
        ClearanceCycle.objects.select_related("policy"),
        pk=cycle_id,
        is_sealed=True,
        policy__is_demo=True,
    )
    if closes_at <= opens_at:
        raise ValidationError({"closes_at": "The closing instant must follow the opening."})
    for value in (opens_at, closes_at):
        day = value.astimezone(ZoneInfo("Asia/Karachi")).date()
        if day < cycle.policy.effective_from or (
            cycle.policy.effective_until and day >= cycle.policy.effective_until
        ):
            raise ValidationError(
                {"cycle_id": "Response instants must fall within the candidate source interval."}
            )
    try:
        with transaction.atomic():
            window = SandboxResponseWindow(
                created_by=actor,
                organization_id=organization_id,
                cycle=cycle,
                opens_at=opens_at,
                closes_at=closes_at,
                source_reference=source_reference,
                source_sha256=source_sha256,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
            )
            window.full_clean()
            window.save(force_insert=True)
    except IntegrityError as exc:
        raise CommandConflict(
            "This cycle already has a response-window snapshot. "
            "Use a new candidate cycle for corrections."
        ) from exc
    record_event(
        actor=actor,
        organization_id=organization_id,
        action="disputes.window_prepared",
        subject=window,
        details={"cycle_id": str(cycle_id), "sandbox": True},
        request_id=request_id,
    )
    return window, False


@transaction.atomic
def stage_draft(
    *,
    actor,
    organization_id,
    claim_id,
    expected_case_version,
    disputed_amount,
    reason_code,
    explanation,
    supporting_statement,
    source_reference,
    idempotency_key,
    request_id=None,
):
    membership = writer(actor, organization_id, AGENCY_ROLES)
    expected_case_version = version(expected_case_version)
    disputed_amount = validation.amount(disputed_amount)
    if reason_code not in REASONS:
        raise ValidationError({"reason_code": "Choose a supported objection category."})
    explanation = validation.text(explanation, "explanation", limit=3000)
    supporting_statement = validation.text(supporting_statement, "supporting_statement", limit=6000)
    source_reference = validation.text(
        source_reference, "source_reference", limit=255, required=False
    )
    payload = {
        "claim_id": str(claim_id),
        "expected_case_version": expected_case_version,
        "disputed_amount": disputed_amount,
        "reason_code": reason_code,
        "explanation": explanation,
        "supporting_statement": supporting_statement,
        "source_reference": source_reference,
    }
    request_hash = digest(payload)
    previous = replay(
        ObjectionDraft, request_hash, agency_id=organization_id, idempotency_key=idempotency_key
    )
    if previous:
        return previous, True
    claim = claim_for_writer(membership, claim_id)
    current = latest_revision(claim.pk)
    if (current.version if current else 0) != expected_case_version:
        raise VersionConflict()
    if Decimal(disputed_amount) > claim.reported_due:
        raise ValidationError(
            {"disputed_amount": "The disputed amount cannot exceed this claim's reported due."}
        )
    window = SandboxResponseWindow.objects.filter(
        cycle_id=claim.invoice.submission.source_import.cycle_id
    ).first()
    snapshot = claim_snapshot(claim)
    content = {**payload, "claim": snapshot, "window": validation.window_snapshot(window)}
    draft = ObjectionDraft.objects.create(
        created_by=actor,
        claim=claim,
        agency_id=organization_id,
        window=window,
        base_version=expected_case_version,
        disputed_amount=disputed_amount,
        reason_code=reason_code,
        explanation=explanation,
        supporting_statement=supporting_statement,
        source_reference=source_reference,
        claim_snapshot=snapshot,
        content_hash=digest(content),
        request_hash=request_hash,
        idempotency_key=idempotency_key,
    )
    record_event(
        actor=actor,
        organization_id=organization_id,
        action="disputes.draft_staged",
        subject=draft,
        details={
            "claim_id": str(claim.pk),
            "content_hash": draft.content_hash,
            "base_version": expected_case_version,
        },
        request_id=request_id,
    )
    return draft, False


def draft_preview(draft):
    current = latest_revision(draft.claim_id)
    current_version = current.version if current else 0
    live_window = SandboxResponseWindow.objects.filter(
        cycle_id=draft.claim.invoice.submission.source_import.cycle_id
    ).first()
    signed = DisputeRevision.objects.filter(draft=draft).first()
    issues = []
    if current_version != draft.base_version:
        issues.append(
            {
                "code": "stale_version",
                "message": "A signed revision changed the case version. Prepare a new draft.",
            }
        )
    if draft.window_id is None:
        issues.append(
            {
                "code": "missing_window",
                "message": (
                    "A candidate response window is required before signing. "
                    "Prepare a new draft after it is configured."
                ),
            }
        )
    elif live_window is None or draft.window_id != live_window.pk:
        issues.append(
            {
                "code": "changed_window",
                "message": "The response-window context has changed. Prepare a new draft.",
            }
        )
    if signed:
        issues.append({"code": "already_signed", "message": "This draft has already been signed."})
    context = {
        "draft_id": str(draft.pk),
        "draft_hash": draft.content_hash,
        "base_version": draft.base_version,
        "current_version": current_version,
        "current_revision_id": str(current.pk) if current else None,
        "window_id": str(live_window.pk) if live_window else None,
        "issues": issues,
    }
    return {
        "current_version": current_version,
        "current_state": "none"
        if not current
        else "withdrawn"
        if current.action == "withdrawn"
        else "open",
        "preview_hash": digest(context),
        "issues": issues,
        "submission_id": str(signed.pk) if signed else None,
        "window": validation.window_snapshot(draft.window),
        "declaration": DECLARATIONS["submit"],
    }


def chronology(claim, simulation_at, current=None):
    minimum = current.simulation_at if current else claim.invoice.submission.simulation_at
    if simulation_at < minimum:
        raise ValidationError(
            {"simulation_at": "Simulation cannot precede the filing or a signed revision."}
        )


def signed_receipt(
    *,
    actor,
    membership,
    claim,
    case,
    previous,
    action,
    disputed_amount,
    simulation_at,
    declaration_type,
    explanation,
    draft=None,
    window=None,
):
    return {
        "schema": "sandbox-dispute-receipt-v1",
        "is_demo": True,
        "case_id": str(case.pk),
        "version": previous.version + 1 if previous else 1,
        "action": action,
        "claim": draft.claim_snapshot if draft else claim_snapshot(claim),
        "disputed_amount": disputed_amount,
        "currency": "PKR",
        "explanation": explanation,
        "reason_code": draft.reason_code if draft else None,
        "supporting_statement": draft.supporting_statement if draft else None,
        "source_reference": draft.source_reference if draft else None,
        "draft_id": str(draft.pk) if draft else None,
        "draft_hash": draft.content_hash if draft else None,
        "window": validation.window_snapshot(window),
        "previous_revision_id": str(previous.pk) if previous else None,
        "previous_revision_hash": previous.content_hash if previous else None,
        "actual_recorded_at": timezone.now().isoformat(),
        "simulation_at": simulation_at.isoformat(),
        "signer": {
            "id": str(actor.pk),
            "username": actor.username,
            "organization_id": str(membership.organization_id),
            "role": membership.role,
        },
        "declaration": DECLARATIONS[declaration_type],
        "financial_effect": "none",
        "enforcement_effect": "none",
    }


def save_revision(
    *,
    actor,
    membership,
    case,
    receipt,
    draft,
    simulation_at,
    idempotency_key,
    request_hash,
    command_type,
    request_id,
):
    try:
        with transaction.atomic():
            revision = DisputeRevision.objects.create(
                created_by=actor,
                created_at=receipt["actual_recorded_at"],
                case=case,
                draft=draft,
                agency_id=membership.organization_id,
                version=receipt["version"],
                action=receipt["action"],
                disputed_amount=receipt["disputed_amount"],
                simulation_at=simulation_at,
                command_type=command_type,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                content_hash=digest(receipt),
                receipt=receipt,
            )
    except IntegrityError as exc:
        raise VersionConflict() from exc
    record_event(
        actor=actor,
        organization_id=membership.organization_id,
        action=f"disputes.{revision.action}",
        subject=revision,
        details={
            "case_id": str(case.pk),
            "version": revision.version,
            "content_hash": revision.content_hash,
            "financial_effect": "none",
        },
        request_id=request_id,
    )
    return revision


@transaction.atomic
def submit_draft(
    *,
    actor,
    organization_id,
    draft_id,
    expected_preview_hash,
    simulation_at,
    declaration_version,
    declaration_accepted,
    idempotency_key,
    request_id=None,
):
    membership = writer(actor, organization_id, {Membership.Role.AGENCY_APPROVER})
    simulation_at = validation.instant(simulation_at)
    request_hash = digest(
        {
            "draft_id": str(draft_id),
            "expected_preview_hash": expected_preview_hash,
            "simulation_at": simulation_at.isoformat(),
            "declaration_version": declaration_version,
            "declaration_accepted": declaration_accepted,
        }
    )
    previous_command = replay(
        DisputeRevision,
        request_hash,
        agency_id=organization_id,
        command_type="submit",
        idempotency_key=idempotency_key,
    )
    if previous_command:
        return previous_command, True
    draft = get_object_or_404(
        drafts_for(membership).select_related(
            "window", "claim__invoice__submission__source_import"
        ),
        pk=draft_id,
    )
    claim = claim_for_writer(membership, draft.claim_id)
    validation.declaration("submit", declaration_version, declaration_accepted)
    preview = draft_preview(draft)
    if preview["submission_id"]:
        raise CommandConflict("This draft already has a signed revision. Read the existing result.")
    if preview["preview_hash"] != expected_preview_hash:
        raise PreviewConflict()
    if preview["current_version"] != draft.base_version:
        raise VersionConflict()
    if preview["issues"]:
        raise ValidationError({"draft": [issue["message"] for issue in preview["issues"]]})
    if not draft.window.opens_at <= simulation_at < draft.window.closes_at:
        raise ResponseWindowClosed()
    previous = latest_revision(claim.pk)
    chronology(claim, simulation_at, previous)
    case, _ = DisputeCase.objects.get_or_create(
        claim=claim,
        defaults={
            "agency_id": claim.invoice.agency_id,
            "channel_id": claim.invoice.channel_id,
            "created_by": actor,
        },
    )
    action = (
        "raised"
        if previous is None
        else "reopened"
        if previous.action == "withdrawn"
        else "amended"
    )
    receipt = signed_receipt(
        actor=actor,
        membership=membership,
        claim=claim,
        case=case,
        previous=previous,
        action=action,
        disputed_amount=money(draft.disputed_amount),
        simulation_at=simulation_at,
        declaration_type="submit",
        explanation=draft.explanation,
        draft=draft,
        window=draft.window,
    )
    return save_revision(
        actor=actor,
        membership=membership,
        case=case,
        receipt=receipt,
        draft=draft,
        simulation_at=simulation_at,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        command_type="submit",
        request_id=request_id,
    ), False


@transaction.atomic
def withdraw(
    *,
    actor,
    organization_id,
    case_id,
    expected_case_version,
    reason,
    simulation_at,
    declaration_version,
    declaration_accepted,
    idempotency_key,
    request_id=None,
):
    membership = writer(actor, organization_id, {Membership.Role.AGENCY_APPROVER})
    simulation_at = validation.instant(simulation_at)
    expected_case_version = version(expected_case_version)
    reason = validation.text(reason, "reason", limit=3000)
    request_hash = digest(
        {
            "case_id": str(case_id),
            "expected_case_version": expected_case_version,
            "reason": reason,
            "simulation_at": simulation_at.isoformat(),
            "declaration_version": declaration_version,
            "declaration_accepted": declaration_accepted,
        }
    )
    previous_command = replay(
        DisputeRevision,
        request_hash,
        agency_id=organization_id,
        command_type="withdraw",
        idempotency_key=idempotency_key,
    )
    if previous_command:
        return previous_command, True
    case = get_object_or_404(DisputeCase.objects.filter(agency_id=organization_id), pk=case_id)
    claim = claim_for_writer(membership, case.claim_id)
    previous = latest_revision(claim.pk)
    if not previous or previous.version != expected_case_version:
        raise VersionConflict()
    if previous.action == "withdrawn":
        raise CommandConflict("This objection is already withdrawn. Its history remains available.")
    validation.declaration("withdraw", declaration_version, declaration_accepted)
    chronology(claim, simulation_at, previous)
    window = SandboxResponseWindow.objects.filter(
        cycle_id=claim.invoice.submission.source_import.cycle_id
    ).first()
    receipt = signed_receipt(
        actor=actor,
        membership=membership,
        claim=claim,
        case=case,
        previous=previous,
        action="withdrawn",
        disputed_amount="0.00",
        simulation_at=simulation_at,
        declaration_type="withdraw",
        explanation=reason,
        window=window,
    )
    return save_revision(
        actor=actor,
        membership=membership,
        case=case,
        receipt=receipt,
        draft=None,
        simulation_at=simulation_at,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        command_type="withdraw",
        request_id=request_id,
    ), False


@transaction.atomic
def add_evidence(
    *,
    actor,
    organization_id,
    claim_id,
    statement,
    source_reference,
    simulation_at,
    declaration_version,
    declaration_accepted,
    idempotency_key,
    request_id=None,
):
    membership = writer(actor, organization_id, AGENCY_ROLES | CHANNEL_ROLES)
    simulation_at = validation.instant(simulation_at)
    statement = validation.text(statement, "statement", limit=6000)
    source_reference = validation.text(
        source_reference, "source_reference", limit=255, required=False
    )
    request_hash = digest(
        {
            "claim_id": str(claim_id),
            "statement": statement,
            "source_reference": source_reference,
            "simulation_at": simulation_at.isoformat(),
            "declaration_version": declaration_version,
            "declaration_accepted": declaration_accepted,
        }
    )
    previous = replay(
        ClaimEvidence,
        request_hash,
        organization_id=organization_id,
        idempotency_key=idempotency_key,
    )
    if previous:
        return previous, True
    claim = claim_for_writer(membership, claim_id)
    validation.declaration("evidence", declaration_version, declaration_accepted)
    chronology(claim, simulation_at)
    window = SandboxResponseWindow.objects.filter(
        cycle_id=claim.invoice.submission.source_import.cycle_id
    ).first()
    timing = validation.evidence_timing(window, simulation_at)
    receipt = {
        "schema": "sandbox-evidence-statement-v1",
        "is_demo": True,
        "claim": claim_snapshot(claim),
        "statement": statement,
        "source_reference": source_reference,
        "actual_recorded_at": timezone.now().isoformat(),
        "simulation_at": simulation_at.isoformat(),
        "window": validation.window_snapshot(window),
        "timing": timing,
        "author": {
            "id": str(actor.pk),
            "username": actor.username,
            "organization_id": str(organization_id),
            "role": membership.role,
        },
        "declaration": DECLARATIONS["evidence"],
        "verification_status": "unverified",
        "financial_effect": "none",
        "enforcement_effect": "none",
    }
    evidence = ClaimEvidence.objects.create(
        created_by=actor,
        created_at=receipt["actual_recorded_at"],
        claim=claim,
        organization_id=organization_id,
        window=window,
        statement=statement,
        source_reference=source_reference,
        simulation_at=simulation_at,
        timing=timing,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        content_hash=digest(receipt),
        receipt=receipt,
    )
    record_event(
        actor=actor,
        organization_id=organization_id,
        action="disputes.evidence_recorded",
        subject=evidence,
        details={
            "claim_id": str(claim.pk),
            "content_hash": evidence.content_hash,
            "timing": timing,
            "financial_effect": "none",
        },
        request_id=request_id,
    )
    return evidence, False
