import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from apps.audit.models import AuditEvent
from apps.complaints.models import ReportedClaim
from apps.complaints.validation import canonical_json, digest
from apps.disputes import services
from apps.disputes.models import ClaimEvidence, DisputeCase, DisputeRevision, ObjectionDraft
from tests.disputes_helpers import (
    draft,
    draft_args,
    evidence_args,
    scoped,
    sign,
    sign_args,
    withdraw_args,
)

pytestmark = pytest.mark.django_db


def test_staged_objection_does_not_open_a_case_or_change_claim(disputes):
    candidate, replayed = draft(disputes)
    assert not replayed and candidate.base_version == 0
    assert DisputeCase.objects.count() == DisputeRevision.objects.count() == 0
    assert services.draft_preview(candidate)["issues"] == []
    disputes.claim.refresh_from_db()
    assert disputes.claim.reported_due == Decimal("1180.00")
    assert AuditEvent.objects.filter(action="disputes.draft_staged").count() == 1


def test_signed_partial_objection_receipt_is_exact_and_scoped(disputes):
    candidate, _ = draft(disputes)
    revision, replayed = sign(disputes, candidate)
    assert not replayed and revision.version == 1 and revision.action == "raised"
    assert revision.receipt["disputed_amount"] == "240.10"
    assert revision.receipt["financial_effect"] == revision.receipt["enforcement_effect"] == "none"
    assert (
        revision.receipt["claim"]["source_submission_hash"]
        == disputes.claim.invoice.submission.content_hash
    )
    assert digest(revision.receipt) == revision.content_hash
    response = scoped(disputes, f"/api/v1/dispute-revisions/{revision.pk}/receipt/")
    assert response.status_code == 200
    assert response.content == canonical_json(revision.receipt).encode()
    assert hashlib.sha256(response.content).hexdigest() == revision.content_hash
    assert response["ETag"] == f'"{revision.content_hash}"'
    assert "no-store" in response["Cache-Control"]


def test_amend_withdraw_reopen_preserves_linked_history(disputes):
    candidate, _ = draft(disputes)
    first, _ = sign(disputes, candidate)
    corrected, _ = draft(disputes, expected_case_version=1, disputed_amount="100.01")
    second, _ = sign(disputes, corrected, simulation_at=datetime(2026, 10, 14, 6, tzinfo=UTC))
    third, _ = services.withdraw(**withdraw_args(disputes, second))
    fresh, _ = draft(disputes, expected_case_version=3, disputed_amount="200.00")
    fourth, _ = sign(disputes, fresh, simulation_at=datetime(2026, 10, 15, 7, tzinfo=UTC))
    assert [r.action for r in (first, second, third, fourth)] == [
        "raised",
        "amended",
        "withdrawn",
        "reopened",
    ]
    assert [r.version for r in (first, second, third, fourth)] == [1, 2, 3, 4]
    for previous, current in zip((first, second, third), (second, third, fourth), strict=True):
        assert current.receipt["previous_revision_id"] == str(previous.pk)
        assert current.receipt["previous_revision_hash"] == previous.content_hash
    assert DisputeCase.objects.count() == 1 and DisputeRevision.objects.count() == 4
    first.refresh_from_db()
    assert first.receipt["disputed_amount"] == "240.10"
    detail = scoped(disputes, f"/api/v1/disputes/{first.case_id}/").json()
    assert detail["current_version"] == 4 and detail["current_disputed_amount"] == "200.00"


def test_late_evidence_and_withdrawal_do_not_reduce_reported_money(disputes):
    candidate, _ = draft(disputes)
    revision, _ = sign(disputes, candidate)
    services.withdraw(
        **withdraw_args(disputes, revision, simulation_at=datetime(2026, 10, 20, 6, tzinfo=UTC))
    )
    memo, replayed = services.add_evidence(**evidence_args(disputes))
    assert not replayed and memo.timing == "late"
    assert memo.receipt["verification_status"] == "unverified"
    assert digest(memo.receipt) == memo.content_hash
    summary = scoped(disputes, "/api/v1/claims/summary/").json()
    assert summary["reported_due_total"] == "1180.00"
    assert summary["disputed_amount_total"] == "0.00"
    assert (
        summary["accepted_credit_total"]
        is summary["verified_settlement_total"]
        is summary["remaining_reportable_balance"]
        is None
    )
    assert ReportedClaim.objects.count() == 2 and ClaimEvidence.objects.count() == 1


def test_grouped_reports_and_claim_context_keep_amounts_distinct(disputes):
    candidate, _ = draft(disputes)
    sign(disputes, candidate)
    detail = scoped(disputes, f"/api/v1/claims/{disputes.claim.pk}/").json()
    assert detail["reported_due"] == "1180.00" and detail["disputed_amount"] == "240.10"
    assert detail["objection_state"] == "open" and detail["objection_version"] == 1
    for group in ("channel", "client", "cycle"):
        response = scoped(disputes, f"/api/v1/claims/breakdown/?group_by={group}")
        assert response.status_code == 200, response.content
        values = response.json()["results"]
        assert len(values) == 1 and values[0]["reported_due_total"] == "1180.00"
        assert values[0]["disputed_amount_total"] == "240.10"
        assert values[0]["active_objection_count"] == 1
    oversight = scoped(
        disputes, "/api/v1/claims/summary/", actor=disputes.auditor, organization=disputes.pba
    ).json()
    assert oversight["reported_due_total"] == "1770.00"
    assert oversight["disputed_amount_total"] == "240.10"


def test_api_stage_sign_and_key_recovery(disputes):
    args = draft_args(disputes)
    payload = {
        key: str(value) if key.endswith("_id") or key == "idempotency_key" else value
        for key, value in args.items()
        if key not in {"actor", "organization_id"}
    }
    scope = {"HTTP_X_ORGANIZATION_ID": str(disputes.agency.pk)}
    response = disputes.http.post(
        "/api/v1/objection-drafts/", payload, content_type="application/json", **scope
    )
    assert response.status_code == 201, response.content
    candidate = ObjectionDraft.objects.get(pk=response.json()["id"])
    disputes.http.force_login(disputes.agency_signer)
    args = sign_args(disputes, candidate)
    payload = {
        "expected_preview_hash": args["expected_preview_hash"],
        "simulation_at": args["simulation_at"].isoformat(),
        "declaration_version": args["declaration_version"],
        "declaration_accepted": True,
        "idempotency_key": str(args["idempotency_key"]),
    }
    signed = disputes.http.post(
        f"/api/v1/objection-drafts/{candidate.pk}/submit/",
        payload,
        content_type="application/json",
        **scope,
    )
    assert signed.status_code == 201, signed.content
    key = args["idempotency_key"]
    recovered = scoped(
        disputes, f"/api/v1/dispute-revisions/?idempotency_key={key}&command_type=submit"
    ).json()
    assert recovered["count"] == 1 and recovered["results"][0]["id"] == signed.json()["id"]
    assert (
        scoped(disputes, f"/api/v1/objection-drafts/{candidate.pk}/").json()["preview"][
            "submission_id"
        ]
        == signed.json()["id"]
    )
    assert (
        json.loads(
            scoped(disputes, f"/api/v1/dispute-revisions/{signed.json()['id']}/receipt/").content
        )["version"]
        == 1
    )


def test_read_filters_remain_scoped(disputes):
    headers = {"HTTP_X_ORGANIZATION_ID": str(disputes.agency.pk)}
    assert (
        disputes.http.get(f"/api/v1/claims/?channel_id={uuid4()}", **headers).json()["count"] == 0
    )
    assert (
        disputes.http.get(
            f"/api/v1/claims/breakdown/?client_id={disputes.foreign_client.pk}", **headers
        ).json()["count"]
        == 0
    )
    assert (
        disputes.http.get("/api/v1/claims/breakdown/?group_by=unknown", **headers).status_code
        == 400
    )
