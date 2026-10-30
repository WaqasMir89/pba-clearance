from datetime import UTC, datetime
from uuid import uuid4

from apps.complaints.models import ReportedClaim
from apps.disputes import services
from apps.disputes.constants import DECLARATIONS
from apps.identity.models import Membership, User
from tests.complaints_helpers import file, row, stage


def prepare_disputes(intake, *, window=True):
    intake.agency_signer = User.objects.create_user(
        username="fictional-agency-signer", is_demo=True
    )
    intake.foreign_signer = User.objects.create_user(
        username="fictional-foreign-signer", is_demo=True
    )
    Membership.objects.create(
        user=intake.agency_signer, organization=intake.agency, role="agency_approver"
    )
    Membership.objects.create(
        user=intake.foreign_signer, organization=intake.other, role="agency_approver"
    )
    batch, _ = stage(
        intake,
        [
            row(),
            row(
                agency_code="sample-other",
                client_code="foreign-client",
                invoice_number="FOREIGN/001",
                principal_amount="500.00",
                gst_amount="90.00",
                invoice_total="590.00",
                reported_due="590.00",
            ),
        ],
    )
    file(intake, batch)
    intake.claim = ReportedClaim.objects.select_related(
        "invoice__submission__source_import__cycle"
    ).get(invoice__agency=intake.agency)
    intake.foreign_claim = ReportedClaim.objects.get(invoice__agency=intake.other)
    intake.response_window = None
    if window:
        intake.response_window, _ = services.create_window(
            actor=intake.policy_actor,
            organization_id=intake.pba.pk,
            cycle_id=intake.cycle.pk,
            opens_at=datetime(2026, 10, 12, 5, tzinfo=UTC),
            closes_at=datetime(2026, 10, 16, 12, tzinfo=UTC),
            source_reference="fictional response source",
            source_sha256="a" * 64,
            idempotency_key=uuid4(),
        )
    return intake


def draft_args(ctx, **changes):
    return {
        **{
            "actor": ctx.member,
            "organization_id": ctx.agency.pk,
            "claim_id": ctx.claim.pk,
            "expected_case_version": 0,
            "disputed_amount": "240.10",
            "reason_code": "amount",
            "explanation": "Fictional invoice line disagreement.",
            "supporting_statement": "Fictional reconciliation note; no verified payment.",
            "source_reference": "fictional evidence reference",
            "idempotency_key": uuid4(),
        },
        **changes,
    }


def draft(ctx, **changes):
    return services.stage_draft(**draft_args(ctx, **changes))


def sign_args(ctx, candidate, **changes):
    return {
        **{
            "actor": ctx.agency_signer,
            "organization_id": ctx.agency.pk,
            "draft_id": candidate.pk,
            "expected_preview_hash": services.draft_preview(candidate)["preview_hash"],
            "simulation_at": datetime(2026, 10, 13, 7, tzinfo=UTC),
            "declaration_version": DECLARATIONS["submit"]["version"],
            "declaration_accepted": True,
            "idempotency_key": uuid4(),
        },
        **changes,
    }


def sign(ctx, candidate, **changes):
    return services.submit_draft(**sign_args(ctx, candidate, **changes))


def withdraw_args(ctx, revision, **changes):
    return {
        **{
            "actor": ctx.agency_signer,
            "organization_id": ctx.agency.pk,
            "case_id": revision.case_id,
            "expected_case_version": revision.version,
            "reason": "Fictional withdrawal after source review.",
            "simulation_at": datetime(2026, 10, 14, 7, tzinfo=UTC),
            "declaration_version": DECLARATIONS["withdraw"]["version"],
            "declaration_accepted": True,
            "idempotency_key": uuid4(),
        },
        **changes,
    }


def evidence_args(ctx, **changes):
    return {
        **{
            "actor": ctx.member,
            "organization_id": ctx.agency.pk,
            "claim_id": ctx.claim.pk,
            "statement": "Fictional supplementary statement. No originals or payment verified.",
            "source_reference": "fictional supplied reference",
            "simulation_at": datetime(2026, 10, 20, 7, tzinfo=UTC),
            "declaration_version": DECLARATIONS["evidence"]["version"],
            "declaration_accepted": True,
            "idempotency_key": uuid4(),
        },
        **changes,
    }


def scoped(ctx, path, *, actor=None, organization=None):
    ctx.http.force_login(actor or ctx.member)
    return ctx.http.get(path, HTTP_X_ORGANIZATION_ID=str((organization or ctx.agency).pk))
