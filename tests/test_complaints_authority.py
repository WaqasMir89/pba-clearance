import base64
import hashlib
from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.conf import settings
from django.db import transaction
from django.test import Client as HttpClient
from django.test import override_settings
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.audit.models import AuditEvent, OutboxEvent
from apps.complaints.errors import AlreadyFiled, CommandConflict, FilingWindowClosed, PreviewChanged
from apps.complaints.models import ComplaintImport, Invoice, ReportedClaim, Submission
from apps.complaints.services import file_import, import_detail, preview_import
from apps.identity.models import Membership, User
from apps.registry.models import ClientAccess, Organization
from tests.complaints_helpers import file, filing_args, row, source_csv, stage

pytestmark = pytest.mark.django_db


def test_session_capabilities_follow_current_sandbox_role(intake):
    from django.test import override_settings

    for user, stage_allowed, file_allowed in [
        (intake.maker, True, False),
        (intake.checker, True, True),
    ]:
        intake.http.force_login(user)
        membership = next(
            item
            for item in intake.http.get("/api/v1/auth/session/").json()["memberships"]
            if item["organization"]["id"] == str(intake.channel.pk)
        )
        assert membership["can_stage_complaints"] is stage_allowed
        assert membership["can_file_complaints"] is file_allowed
        assert membership["can_view_claims"] is True
    with override_settings(ENVIRONMENT="production"):
        membership = intake.http.get("/api/v1/auth/session/").json()["memberships"][0]
        assert not membership["can_stage_complaints"]
        assert not membership["can_file_complaints"]


def test_intake_options_bound_and_filter_scoped_clients(intake):
    from apps.registry.models import Client, ClientAccess

    clients = Client.objects.bulk_create(
        [
            Client(
                code=f"lookup-{i}",
                legal_name=f"Lookup {i}",
                is_demo=True,
                created_by=intake.maker,
            )
            for i in range(101)
        ]
    )
    ClientAccess.objects.bulk_create(
        [ClientAccess(client=client, organization=intake.channel) for client in clients]
    )
    intake.http.force_login(intake.maker)
    headers = {"HTTP_X_ORGANIZATION_ID": str(intake.channel.pk)}
    result = intake.http.get("/api/v1/complaint-intake/options/", **headers).json()
    assert len(result["clients"]) == result["client_limit"] == 100
    assert result["client_count"] >= 101
    filtered = intake.http.get("/api/v1/complaint-intake/options/?q=lookup-100", **headers).json()
    assert filtered["client_count"] == 1
    assert filtered["clients"][0]["code"] == "lookup-100"


def test_stage_key_replays_original_and_rejects_changed_source(intake):
    key = uuid4()
    first, replayed = stage(intake, idempotency_key=key)
    assert not replayed
    again, replayed = stage(intake, idempotency_key=key)
    assert replayed and again.pk == first.pk
    with pytest.raises(CommandConflict):
        stage(intake, [row(invoice_number="different")], idempotency_key=key)
    assert ComplaintImport.objects.count() == 1
    assert AuditEvent.objects.filter(action="complaints.import_staged").count() == 1


def test_filing_key_recovers_without_reapplying_the_command(intake):
    batch, _ = stage(intake)
    arguments = filing_args(intake, batch)
    first, _ = file_import(**arguments)
    with patch("apps.complaints.services._filing_clock", side_effect=FilingWindowClosed):
        recovered, replayed = file_import(**arguments)
    assert recovered.id == first.id and replayed
    assert Submission.objects.count() == Invoice.objects.count() == 1
    assert AuditEvent.objects.filter(action="complaints.submitted").count() == 1
    with pytest.raises(CommandConflict):
        file_import(
            **{**arguments, "simulation_at": arguments["simulation_at"] + timedelta(minutes=1)}
        )
    with pytest.raises(AlreadyFiled):
        file_import(**{**arguments, "idempotency_key": uuid4()})


def test_stale_review_does_not_silently_change_filing_totals(intake):
    first, _ = stage(intake)
    second, _ = stage(intake)
    old = preview_import(second)
    file(intake, first)
    with pytest.raises(PreviewChanged):
        file(intake, second, expected_preview_hash=old["preview_hash"])
    assert Submission.objects.count() == 1
    assert preview_import(second)["counts"]["duplicate"] == 1


@pytest.mark.parametrize(
    "instant,allowed",
    [
        (datetime(2026, 10, 5, 3, 59, 59, tzinfo=UTC), False),
        (datetime(2026, 10, 5, 4, tzinfo=UTC), True),
        (datetime(2026, 10, 9, 11, 59, 59, 999999, tzinfo=UTC), True),
        (datetime(2026, 10, 9, 12, tzinfo=UTC), False),
        (datetime(2026, 10, 10, 4, tzinfo=UTC), False),
    ],
)
def test_explicit_simulation_window_boundaries(intake, instant, allowed):
    batch, _ = stage(intake)
    if allowed:
        submission, _ = file(intake, batch, simulation_at=instant)
        assert submission.simulation_at == instant
        assert submission.submitted_at != instant
    else:
        with pytest.raises(FilingWindowClosed):
            file(intake, batch, simulation_at=instant)
        assert not Submission.objects.exists()


def test_simulation_cannot_precede_reported_invoice_or_delivery(intake):
    batch, _ = stage(intake, [row(invoice_date="2026-10-08", invoice_delivered_on="2026-10-08")])
    with pytest.raises(ValidationError, match="simulation"):
        file(intake, batch)


def test_preparer_and_pba_roles_cannot_file(intake):
    batch, _ = stage(intake)
    with pytest.raises(PermissionDenied):
        file(intake, batch, actor=intake.maker)
    with pytest.raises(PermissionDenied):
        file(intake, batch, actor=intake.officer, organization_id=intake.pba.id)
    assert not Submission.objects.exists()


@pytest.mark.parametrize(
    "condition", ["production", "real_user", "real_channel", "revoked", "expired"]
)
def test_sandbox_and_current_authority_are_required(intake, condition):
    batch, _ = stage(intake)
    if condition == "real_user":
        User.objects.filter(pk=intake.checker.pk).update(is_demo=False)
    elif condition == "real_channel":
        Organization.objects.filter(pk=intake.channel.pk).update(is_demo=False)
    elif condition == "revoked":
        Membership.objects.filter(user=intake.checker, organization=intake.channel).update(
            revoked_at=timezone.now()
        )
    elif condition == "expired":
        Membership.objects.filter(user=intake.checker, organization=intake.channel).update(
            starts_at=timezone.now() - timedelta(days=2), ends_at=timezone.now() - timedelta(days=1)
        )
    with override_settings(
        ENVIRONMENT="production" if condition == "production" else "development"
    ):
        with pytest.raises(PermissionDenied):
            file(intake, batch)
    assert not Invoice.objects.exists()


def test_declaration_is_required_and_versioned(intake):
    batch, _ = stage(intake)
    for changes in [{"declaration_accepted": False}, {"declaration_version": "obsolete"}]:
        with pytest.raises(ValidationError):
            file(intake, batch, **changes)
    assert not Submission.objects.exists()


def test_failure_after_business_writes_rolls_everything_back(intake):
    batch, _ = stage(intake)
    before_audit, before_outbox = AuditEvent.objects.count(), OutboxEvent.objects.count()
    with patch(
        "apps.audit.services.OutboxEvent.objects.create", side_effect=RuntimeError("simulated")
    ):
        with pytest.raises(RuntimeError):
            file(intake, batch)
    assert not Submission.objects.exists() and not Invoice.objects.exists()
    assert not ReportedClaim.objects.exists()
    assert (
        AuditEvent.objects.count() == before_audit and OutboxEvent.objects.count() == before_outbox
    )


def test_agency_only_sees_its_claims_and_never_the_multi_agency_source(intake):
    batch, _ = stage(
        intake,
        [
            row(),
            row(
                invoice_number="OTHER/1",
                agency_code=intake.other.code,
                client_code=intake.foreign_client.code,
            ),
        ],
    )
    submission, _ = file(intake, batch)
    claims = list(ReportedClaim.objects.select_related("invoice").order_by("invoice__agency_id"))
    own = next(c for c in claims if c.invoice.agency_id == intake.agency.id)
    other = next(c for c in claims if c.invoice.agency_id == intake.other.id)
    intake.http.force_login(intake.member)
    scope = {"HTTP_X_ORGANIZATION_ID": str(intake.agency.id)}
    response = intake.http.get("/api/v1/claims/", **scope)
    assert response.status_code == 200 and response.json()["count"] == 1
    assert response.json()["results"][0]["id"] == str(own.id)
    assert intake.foreign_client.legal_name not in response.content.decode()
    assert intake.http.get(f"/api/v1/claims/{other.id}/", **scope).status_code == 404
    assert intake.http.get(f"/api/v1/complaint-imports/{batch.id}/", **scope).status_code == 403
    assert (
        intake.http.get(f"/api/v1/complaint-submissions/{submission.id}/", **scope).status_code
        == 403
    )
    assert (
        intake.http.get(
            f"/api/v1/complaint-submissions/{submission.id}/receipt/", **scope
        ).status_code
        == 403
    )
    assert AuditEvent.objects.filter(action="access.denied", actor=intake.member).count() >= 4
    # Historical case access comes from participation, not a later registry grant.
    ClientAccess.objects.filter(client=intake.client, organization=intake.agency).delete()
    assert intake.http.get(f"/api/v1/claims/{own.id}/", **scope).status_code == 200


def test_another_channel_cannot_read_or_file_a_foreign_import(intake):
    batch, _ = stage(intake)
    intake.http.force_login(intake.other_checker)
    scope = {"HTTP_X_ORGANIZATION_ID": str(intake.other_channel.id)}
    assert intake.http.get(f"/api/v1/complaint-imports/{batch.id}/", **scope).status_code == 404
    assert intake.http.get("/api/v1/complaint-imports/", **scope).json()["count"] == 0
    from django.http import Http404

    with pytest.raises(Http404):
        file(intake, batch, actor=intake.other_checker, organization_id=intake.other_channel.id)


def test_pba_oversight_reads_filed_claims_but_policy_role_does_not(intake):
    batch, _ = stage(intake)
    submission, _ = file(intake, batch)
    intake.http.force_login(intake.auditor)
    scope = {"HTTP_X_ORGANIZATION_ID": str(intake.pba.id)}
    assert (
        intake.http.get("/api/v1/claims/summary/", **scope).json()["reported_due_total"]
        == "1180.00"
    )
    assert (
        intake.http.get(f"/api/v1/complaint-submissions/{submission.id}/", **scope).status_code
        == 200
    )
    assert intake.http.get(f"/api/v1/complaint-imports/{batch.id}/", **scope).status_code == 403
    intake.http.force_login(intake.policy_actor)
    assert intake.http.get("/api/v1/claims/", **scope).status_code == 403


def test_channel_review_lookup_and_historical_snapshot_are_recoverable(intake):
    key = uuid4()
    batch, _ = stage(intake, idempotency_key=key)
    preview = preview_import(batch)
    submission, _ = file(intake, batch)
    intake.http.force_login(intake.maker)
    scope = {"HTTP_X_ORGANIZATION_ID": str(intake.channel.id)}
    listed = intake.http.get(f"/api/v1/complaint-imports/?idempotency_key={key}", **scope).json()
    assert listed["count"] == 1 and listed["results"][0]["submission_id"] == str(submission.id)
    detail = intake.http.get(f"/api/v1/complaint-imports/{batch.id}/", **scope).json()
    assert (
        not detail["preview_current"]
        and detail["preview"]["preview_hash"] == preview["preview_hash"]
    )
    assert detail["preview"]["rows"][0]["status"] == "ready"
    assert "source_bytes" not in detail


def test_csv_writes_require_csrf_and_explicit_timezone(intake):
    http = HttpClient(enforce_csrf_checks=True)
    http.force_login(intake.maker)
    response = http.post(
        "/api/v1/complaint-imports/",
        {},
        content_type="application/json",
        HTTP_X_ORGANIZATION_ID=str(intake.channel.id),
    )
    assert response.status_code == 403
    batch, _ = stage(intake)
    intake.http.force_login(intake.checker)
    data = filing_args(intake, batch)
    for key in ["actor", "organization_id", "import_id"]:
        data.pop(key)
    data["idempotency_key"] = str(data["idempotency_key"])
    data["simulation_at"] = "2026-10-06T12:00:00"
    response = intake.http.post(
        f"/api/v1/complaint-imports/{batch.id}/submit/",
        data,
        content_type="application/json",
        HTTP_X_ORGANIZATION_ID=str(intake.channel.id),
    )
    assert response.status_code == 400 and not Submission.objects.exists()


def test_oversize_json_is_rejected_before_drf_stream_parsing(intake):
    response = intake.http.generic(
        "POST",
        "/api/v1/complaint-imports/",
        data=b"x" * (settings.DATA_UPLOAD_MAX_MEMORY_SIZE + 1),
        content_type="application/json",
    )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "request_too_large"
    assert response["Cache-Control"] == "no-store, private"


def test_bad_base64_and_unsafe_filenames_do_not_stage_partial_sources(intake):
    intake.http.force_login(intake.maker)
    data = {
        "cycle_id": str(intake.cycle.id),
        "source_filename": "fictional.csv",
        "csv_base64": "!!!",
        "idempotency_key": str(uuid4()),
    }
    scope = {"HTTP_X_ORGANIZATION_ID": str(intake.channel.id)}
    assert (
        intake.http.post(
            "/api/v1/complaint-imports/", data, content_type="application/json", **scope
        ).status_code
        == 400
    )
    data.update(
        csv_base64=base64.b64encode(source_csv([row()])).decode(), source_filename="../escape.csv"
    )
    assert (
        intake.http.post(
            "/api/v1/complaint-imports/", data, content_type="application/json", **scope
        ).status_code
        == 400
    )
    assert not ComplaintImport.objects.exists()


def test_receipt_download_has_the_recorded_digest_and_no_private_review_blob(intake):
    batch, _ = stage(intake)
    submission, _ = file(intake, batch)
    intake.http.force_login(intake.checker)
    scope = {"HTTP_X_ORGANIZATION_ID": str(intake.channel.id)}
    receipt = intake.http.get(f"/api/v1/complaint-submissions/{submission.id}/receipt/", **scope)
    assert hashlib.sha256(receipt.content).hexdigest() == submission.content_hash
    assert "preview_snapshot" not in receipt.json()
    with transaction.atomic():
        assert import_detail(batch)["preview"]["preview_hash"] == submission.receipt["preview_hash"]
