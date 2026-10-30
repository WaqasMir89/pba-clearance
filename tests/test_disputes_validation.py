from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from rest_framework.exceptions import ValidationError

from apps.complaints.errors import CommandConflict
from apps.disputes import services
from apps.disputes.errors import PreviewConflict, ResponseWindowClosed, VersionConflict
from apps.disputes.models import ClaimEvidence, DisputeRevision, ObjectionDraft
from tests.disputes_helpers import (
    draft,
    draft_args,
    evidence_args,
    prepare_disputes,
    scoped,
    sign,
    sign_args,
    withdraw_args,
)

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    "value",
    [
        "NaN",
        "Infinity",
        "-1",
        "+1",
        "1.001",
        "1e2",
        "1,000",
        "",
        "0.00",
        "99999999999999999.00",
        1,
        1.2,
        None,
        True,
    ],
)
def test_ambiguous_or_nonpositive_objection_amounts_are_rejected(disputes, value):
    with pytest.raises(ValidationError):
        draft(disputes, disputed_amount=value)
    assert ObjectionDraft.objects.count() == 0


def test_partial_and_full_objections_cannot_exceed_reported_due(disputes):
    with pytest.raises(ValidationError):
        draft(disputes, disputed_amount="1180.01")
    tiny, _ = draft(disputes, disputed_amount="0.01")
    full, _ = draft(disputes, disputed_amount="1180.00")
    assert tiny.disputed_amount == "0.01" and full.disputed_amount == "1180.00"
    result, _ = sign(disputes, full)
    assert result.receipt["disputed_amount"] == "1180.00"
    assert scoped(disputes, "/api/v1/claims/summary/").json()["reported_due_total"] == "1180.00"


@pytest.mark.parametrize(
    "field,value",
    [
        ("reason_code", "unsupported"),
        ("explanation", " "),
        ("supporting_statement", ""),
        ("source_reference", "a" * 256),
        ("explanation", "x" * 3001),
        ("supporting_statement", "x" * 6001),
        ("explanation", "bad\x00text"),
        ("supporting_statement", "bad\u202etext"),
        ("expected_case_version", -1),
        ("expected_case_version", True),
    ],
)
def test_draft_fields_are_bounded_and_explicit(disputes, field, value):
    with pytest.raises(ValidationError):
        draft(disputes, **{field: value})


@pytest.mark.parametrize("offset,accepted", [(-1, False), (0, True), (1, True)])
def test_response_open_boundary(disputes, offset, accepted):
    candidate, _ = draft(disputes)
    at = disputes.response_window.opens_at + timedelta(microseconds=offset)
    if accepted:
        assert sign(disputes, candidate, simulation_at=at)[0].version == 1
    else:
        with pytest.raises(ResponseWindowClosed):
            sign(disputes, candidate, simulation_at=at)


@pytest.mark.parametrize("offset,accepted", [(-1, True), (0, False), (1, False)])
def test_response_close_boundary(disputes, offset, accepted):
    candidate, _ = draft(disputes)
    at = disputes.response_window.closes_at + timedelta(microseconds=offset)
    if accepted:
        sign(disputes, candidate, simulation_at=at)
    else:
        with pytest.raises(ResponseWindowClosed):
            sign(disputes, candidate, simulation_at=at)
    memo, _ = services.add_evidence(**evidence_args(disputes, simulation_at=at))
    assert memo.timing == ("within_window" if offset < 0 else "late")


def test_missing_window_blocks_signing_but_not_supplementary_evidence(intake):
    ctx = prepare_disputes(intake, window=False)
    candidate, _ = draft(ctx)
    assert services.draft_preview(candidate)["issues"][0]["code"] == "missing_window"
    with pytest.raises(ValidationError):
        sign(ctx, candidate)
    memo, _ = services.add_evidence(**evidence_args(ctx))
    assert memo.timing == "window_unknown" and memo.window_id is None
    assert DisputeRevision.objects.count() == 0


def test_naive_or_backdated_simulation_is_rejected(disputes):
    candidate, _ = draft(disputes)
    with pytest.raises(ValidationError):
        sign(disputes, candidate, simulation_at=datetime(2026, 10, 13, 12))
    first, _ = sign(disputes, candidate)
    corrected, _ = draft(disputes, expected_case_version=1)
    with pytest.raises(ValidationError):
        sign(disputes, corrected, simulation_at=datetime(2026, 10, 13, 6, tzinfo=UTC))
    with pytest.raises(ValidationError):
        services.add_evidence(
            **evidence_args(disputes, simulation_at=datetime(2026, 10, 5, 7, tzinfo=UTC))
        )
    assert first.version == 1 and ClaimEvidence.objects.count() == 0


def test_closed_window_does_not_allow_backdated_reopening(disputes):
    candidate, _ = draft(disputes)
    first, _ = sign(disputes, candidate)
    services.withdraw(
        **withdraw_args(disputes, first, simulation_at=datetime(2026, 10, 20, 6, tzinfo=UTC))
    )
    reopened, _ = draft(disputes, expected_case_version=2)
    with pytest.raises(ValidationError):
        sign(disputes, reopened, simulation_at=datetime(2026, 10, 15, 7, tzinfo=UTC))


def test_old_draft_and_stale_preview_cannot_overwrite_signed_revision(disputes):
    first, _ = draft(disputes)
    second, _ = draft(disputes, disputed_amount="50.00")
    old_args = sign_args(disputes, second)
    sign(disputes, first)
    with pytest.raises(PreviewConflict):
        services.submit_draft(**old_args)
    with pytest.raises(VersionConflict):
        sign(disputes, second)
    with pytest.raises(VersionConflict):
        draft(disputes, expected_case_version=0)
    assert DisputeRevision.objects.count() == 1


def test_draft_and_sign_keys_bind_payload_and_replay_original(disputes):
    args = draft_args(disputes)
    candidate, _ = services.stage_draft(**args)
    assert services.stage_draft(**args)[1] is True
    with pytest.raises(CommandConflict):
        services.stage_draft(**{**args, "disputed_amount": "5.00"})
    signing = sign_args(disputes, candidate)
    posted, _ = services.submit_draft(**signing)
    assert services.submit_draft(**signing)[0].pk == posted.pk
    assert services.submit_draft(**signing)[1] is True
    assert services.stage_draft(**args)[0].pk == candidate.pk
    with pytest.raises(CommandConflict):
        services.submit_draft(**{**signing, "simulation_at": datetime(2026, 10, 20, 7, tzinfo=UTC)})
    with pytest.raises(CommandConflict):
        sign(disputes, candidate)


def test_withdrawal_and_evidence_keys_recover_after_case_changes(disputes):
    candidate, _ = draft(disputes)
    signed, _ = sign(disputes, candidate)
    withdrawal = withdraw_args(disputes, signed)
    posted, _ = services.withdraw(**withdrawal)
    assert services.withdraw(**withdrawal)[0].pk == posted.pk
    with pytest.raises(CommandConflict):
        services.withdraw(**{**withdrawal, "reason": "changed reason"})
    with pytest.raises(VersionConflict):
        services.withdraw(**{**withdrawal, "idempotency_key": uuid4()})
    memo_args = evidence_args(disputes)
    memo, _ = services.add_evidence(**memo_args)
    assert services.add_evidence(**memo_args)[0].pk == memo.pk
    assert services.add_evidence(**memo_args)[1]
    with pytest.raises(CommandConflict):
        services.add_evidence(**{**memo_args, "statement": "changed statement"})


@pytest.mark.parametrize("command", ["submit", "withdraw", "evidence"])
def test_each_mutation_requires_its_current_declaration(disputes, command):
    candidate, _ = draft(disputes)
    if command == "submit":
        with pytest.raises(ValidationError):
            sign(disputes, candidate, declaration_accepted=False)
    elif command == "withdraw":
        signed, _ = sign(disputes, candidate)
        with pytest.raises(ValidationError):
            services.withdraw(**withdraw_args(disputes, signed, declaration_version="wrong"))
    else:
        with pytest.raises(ValidationError):
            services.add_evidence(**evidence_args(disputes, declaration_accepted=False))


def test_api_requires_decimal_strings_and_offset_and_rejects_unknown_filters(disputes):
    args = draft_args(disputes)
    data = {
        key: str(value) if key in {"claim_id", "idempotency_key"} else value
        for key, value in args.items()
        if key not in {"actor", "organization_id"}
    }
    scope = {"HTTP_X_ORGANIZATION_ID": str(disputes.agency.pk)}
    assert (
        disputes.http.post(
            "/api/v1/objection-drafts/",
            {**data, "disputed_amount": 240.10},
            content_type="application/json",
            **scope,
        ).status_code
        == 400
    )
    candidate, _ = draft(disputes)
    args = sign_args(disputes, candidate)
    disputes.http.force_login(disputes.agency_signer)
    bad = {
        "expected_preview_hash": args["expected_preview_hash"],
        "simulation_at": "2026-10-13T12:00",
        "declaration_version": args["declaration_version"],
        "declaration_accepted": True,
        "idempotency_key": str(args["idempotency_key"]),
    }
    assert (
        disputes.http.post(
            f"/api/v1/objection-drafts/{candidate.pk}/submit/",
            bad,
            content_type="application/json",
            **scope,
        ).status_code
        == 400
    )
    assert scoped(disputes, "/api/v1/disputes/?claim_id=bad").status_code == 400
    assert scoped(disputes, "/api/v1/dispute-revisions/?command_type=bad").status_code == 400


def test_evidence_does_not_change_open_disputed_amount(disputes):
    candidate, _ = draft(disputes)
    sign(disputes, candidate)
    services.add_evidence(
        **evidence_args(
            disputes,
            statement="Fictional screenshot statement claims payment; it remains unverified.",
        )
    )
    summary = scoped(disputes, "/api/v1/claims/summary/").json()
    assert (
        summary["reported_due_total"] == "1180.00" and summary["disputed_amount_total"] == "240.10"
    )
    assert summary["verified_settlement_total"] is None


def test_exact_aggregates_do_not_use_binary_float(disputes):
    candidate, _ = draft(disputes, disputed_amount="0.10")
    sign(disputes, candidate)
    other, _ = draft(
        disputes,
        actor=disputes.foreign_signer,
        organization_id=disputes.other.pk,
        claim_id=disputes.foreign_claim.pk,
        disputed_amount="0.20",
    )
    sign(disputes, other, actor=disputes.foreign_signer, organization_id=disputes.other.pk)
    summary = scoped(
        disputes, "/api/v1/claims/summary/", actor=disputes.auditor, organization=disputes.pba
    ).json()
    assert summary["disputed_amount_total"] == "0.30"
    assert Decimal(summary["reported_due_total"]) == Decimal("1770.00")
