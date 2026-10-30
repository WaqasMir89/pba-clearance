import json
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, transaction
from django.test import Client as HttpClient
from django.test import override_settings
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied
from rest_framework.exceptions import ValidationError as ApiValidationError

from apps.audit.models import AuditEvent, OutboxEvent
from apps.identity.models import Membership, User
from apps.registry.models import Client, Organization
from apps.registry.services import create_client, create_organization

pytestmark = pytest.mark.django_db


def scoped_get(workspace, path, organization=None):
    return workspace.http.get(
        path, HTTP_X_ORGANIZATION_ID=str((organization or workspace.agency).id)
    )


def test_login_requires_csrf_and_logout_revokes_session(workspace):
    workspace.member.set_password("unique-test-password-123")
    workspace.member.save()
    http = HttpClient(enforce_csrf_checks=True)
    credentials = {"username": "member", "password": "unique-test-password-123"}
    denied = http.post("/api/v1/auth/login/", credentials, content_type="application/json")
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "csrf_failed"
    token = http.get("/api/v1/auth/csrf/").json()["csrf_token"]
    response = http.post(
        "/api/v1/auth/login/", credentials, content_type="application/json", HTTP_X_CSRFTOKEN=token
    )
    assert response.status_code == 200
    assert response.json()["memberships"][0]["role"] == "agency_preparer"
    assert http.get("/api/v1/auth/session/").status_code == 200
    assert http.post("/api/v1/auth/logout/", {}, content_type="application/json").status_code == 403
    # Login rotates the CSRF token; refresh it before the next command.
    token = http.get("/api/v1/auth/csrf/").json()["csrf_token"]
    assert (
        http.post(
            "/api/v1/auth/logout/", {}, content_type="application/json", HTTP_X_CSRFTOKEN=token
        ).status_code
        == 204
    )
    assert http.get("/api/v1/auth/session/").status_code == 401


def test_bad_credentials_are_generic(workspace):
    response = HttpClient().post(
        "/api/v1/auth/login/",
        {"username": "missing", "password": "wrong"},
        content_type="application/json",
    )
    assert response.status_code == 401
    assert response.json()["error"]["message"] == "The username or password is incorrect."


def test_login_is_rate_limited(workspace):
    http = HttpClient()
    for _ in range(10):
        response = http.post("/api/v1/auth/login/", {}, content_type="application/json")
        assert response.status_code == 400
    assert http.post("/api/v1/auth/login/", {}, content_type="application/json").status_code == 429


def test_session_lists_only_current_memberships(workspace):
    session = workspace.http.get("/api/v1/auth/session/").json()
    assert [m["organization"]["id"] for m in session["memberships"]] == [str(workspace.agency.id)]
    assert session["enforcement_enabled"] is False


def test_organization_and_client_reads_are_scoped(workspace):
    orgs = scoped_get(workspace, "/api/v1/registry/organizations/").json()["results"]
    assert [o["id"] for o in orgs] == [str(workspace.agency.id)]
    clients = scoped_get(workspace, "/api/v1/registry/clients/").json()["results"]
    assert [c["id"] for c in clients] == [str(workspace.client.id)]
    assert (
        scoped_get(
            workspace, f"/api/v1/registry/clients/{workspace.foreign_client.id}/"
        ).status_code
        == 404
    )
    assert (
        scoped_get(workspace, f"/api/v1/registry/organizations/{workspace.other.id}/").status_code
        == 404
    )


def test_forged_workspace_is_denied_and_audited(workspace):
    response = scoped_get(workspace, "/api/v1/registry/clients/", workspace.other)
    assert response.status_code == 403
    event = AuditEvent.objects.get(action="access.denied")
    assert event.actor_id == workspace.member.id
    assert event.organization_id is None
    assert str(workspace.foreign_client.id) not in response.content.decode()


def test_missing_workspace_cannot_default_to_privileged_scope(workspace):
    assert workspace.http.get("/api/v1/registry/clients/").status_code == 400


@pytest.mark.parametrize("state", ["revoked", "expired", "future", "inactive_org", "invalid_role"])
def test_live_membership_guards(workspace, state):
    now = timezone.now()
    if state == "revoked":
        Membership.objects.filter(pk=workspace.membership.pk).update(revoked_at=now)
    elif state == "expired":
        Membership.objects.filter(pk=workspace.membership.pk).update(
            starts_at=now - timedelta(days=2), ends_at=now - timedelta(days=1)
        )
    elif state == "future":
        Membership.objects.filter(pk=workspace.membership.pk).update(
            starts_at=now + timedelta(days=1)
        )
    elif state == "inactive_org":
        Organization.objects.filter(pk=workspace.agency.pk).update(is_active=False)
    else:
        Membership.objects.filter(pk=workspace.membership.pk).update(role="pba_registry")
    assert scoped_get(workspace, "/api/v1/registry/clients/").status_code == 403
    assert workspace.http.get("/api/v1/auth/session/").json()["memberships"] == []


def test_inactive_user_loses_session_access(workspace):
    User.objects.filter(pk=workspace.member.pk).update(is_active=False)
    assert workspace.http.get("/api/v1/auth/session/").status_code == 401


def test_superuser_has_no_implicit_business_scope(workspace):
    admin = User.objects.create_superuser(username="operator", password="irrelevant")
    workspace.http.force_login(admin)
    assert scoped_get(workspace, "/api/v1/registry/clients/", workspace.pba).status_code == 403


def test_membership_model_rejects_cross_kind_role(workspace):
    workspace.membership.role = "pba_registry"
    with pytest.raises(ValidationError):
        workspace.membership.full_clean()


def test_membership_interval_is_database_constrained(workspace):
    with pytest.raises(IntegrityError), transaction.atomic():
        Membership.objects.filter(pk=workspace.membership.pk).update(
            ends_at=workspace.membership.starts_at
        )


def test_pba_reader_can_read_but_cannot_write(workspace):
    workspace.http.force_login(workspace.auditor)
    assert scoped_get(workspace, "/api/v1/registry/clients/", workspace.pba).json()["count"] == 2
    response = workspace.http.post(
        "/api/v1/registry/organizations/",
        {"legal_name": "Attempted", "code": "attempted", "kind": "agency"},
        content_type="application/json",
        HTTP_X_ORGANIZATION_ID=str(workspace.pba.id),
    )
    assert response.status_code == 403
    assert not Organization.objects.filter(code="attempted").exists()


def test_officer_creates_registry_entry_with_durable_history(workspace):
    workspace.http.force_login(workspace.officer)
    response = workspace.http.post(
        "/api/v1/registry/organizations/",
        {"legal_name": "Sample Added Agency", "code": "ADDED", "kind": "agency"},
        content_type="application/json",
        HTTP_X_ORGANIZATION_ID=str(workspace.pba.id),
    )
    assert response.status_code == 201
    assert response.json()["code"] == "added"
    event = AuditEvent.objects.get(action="registry.organization_created")
    assert event.subject_id == Organization.objects.get(code="added").id
    assert OutboxEvent.objects.get(audit_event=event).state == "pending"


def test_duplicate_identifiers_rejected_without_new_history(workspace):
    with pytest.raises(ValidationError):
        create_organization(
            actor=workspace.officer,
            organization_id=workspace.pba.id,
            legal_name="Different Name",
            code=workspace.agency.code.upper(),
            kind="agency",
        )
    assert not AuditEvent.objects.exists()


def test_client_creation_grants_visibility_without_creating_appointment(workspace):
    client = create_client(
        actor=workspace.officer,
        organization_id=workspace.pba.id,
        legal_name="New Sample Client",
        code="new-client",
        participant_ids=[workspace.agency.id, workspace.channel.id],
    )
    assert client.access_grants.count() == 2
    assert scoped_get(workspace, f"/api/v1/registry/clients/{client.id}/").status_code == 200


def test_demo_workspace_cannot_create_unlabelled_registry_examples(workspace):
    Organization.objects.filter(pk=workspace.pba.pk).update(is_demo=True)
    organization = create_organization(
        actor=workspace.officer,
        organization_id=workspace.pba.id,
        legal_name="Fictional Added Agency",
        code="fictional-added",
        kind="agency",
    )
    client = create_client(
        actor=workspace.officer,
        organization_id=workspace.pba.id,
        legal_name="Fictional Added Client",
        code="fictional-added-client",
        participant_ids=[organization.pk],
    )
    assert organization.is_demo and client.is_demo


def test_invalid_participant_rolls_back_creation(workspace):
    with pytest.raises(ApiValidationError, match="existing, active"):
        create_client(
            actor=workspace.officer,
            organization_id=workspace.pba.id,
            legal_name="Invalid Client",
            code="invalid-client",
            participant_ids=[],
        )
    assert not Client.objects.filter(code="invalid-client").exists()
    assert not AuditEvent.objects.exists()


def test_failed_outbox_rolls_back_business_record_and_audit(workspace):
    with patch(
        "apps.audit.services.OutboxEvent.objects.create", side_effect=RuntimeError("failed")
    ):
        with pytest.raises(RuntimeError):
            create_organization(
                actor=workspace.officer,
                organization_id=workspace.pba.id,
                legal_name="Rolled Back",
                code="rollback-org",
                kind="agency",
            )
    assert not Organization.objects.filter(code="rollback-org").exists()
    assert not AuditEvent.objects.exists()


def test_production_registry_writes_are_disabled(workspace):
    with override_settings(ENVIRONMENT="production"), pytest.raises(PermissionDenied):
        create_organization(
            actor=workspace.officer,
            organization_id=workspace.pba.id,
            legal_name="Blocked",
            code="production-block",
            kind="agency",
        )


def test_audit_reader_is_explicit_and_scoped(workspace):
    assert scoped_get(workspace, "/api/v1/audit/").status_code == 403
    AuditEvent.objects.create(
        organization_id=workspace.other.id,
        action="private.example",
        subject_type="registry.organization",
        subject_id=workspace.other.id,
    )
    workspace.http.force_login(workspace.officer)
    result = scoped_get(workspace, "/api/v1/audit/", workspace.pba)
    assert result.status_code == 200
    assert result.json()["count"] == 0


def test_demo_requires_password_and_development(workspace, monkeypatch):
    monkeypatch.delenv("CLEARANCE_DEMO_PASSWORD", raising=False)
    with patch("sys.stdin.isatty", return_value=False), pytest.raises(CommandError):
        call_command("seed_demo")
    with override_settings(ENVIRONMENT="production"), pytest.raises(CommandError):
        call_command("seed_demo")


def test_api_write_cannot_use_session_without_csrf(workspace):
    http = HttpClient(enforce_csrf_checks=True)
    http.force_login(workspace.officer)
    response = http.post(
        "/api/v1/registry/clients/",
        json.dumps({}),
        content_type="application/json",
        HTTP_X_ORGANIZATION_ID=str(workspace.pba.id),
    )
    assert response.status_code == 403


def test_demo_is_explicit_idempotent_and_preserves_revocation(monkeypatch):
    monkeypatch.setenv("CLEARANCE_DEMO_PASSWORD", "local-example-password-582")
    with override_settings(ENVIRONMENT="development"):
        call_command("seed_demo")
        count = AuditEvent.objects.count()
        membership = Membership.objects.filter(user__username="demo.channel").first()
        Membership.objects.filter(pk=membership.pk).update(revoked_at=timezone.now())
        call_command("seed_demo")
    assert User.objects.filter(is_demo=True).count() == 6
    assert Organization.objects.filter(is_demo=True).count() == 5
    assert Client.objects.filter(is_demo=True).count() == 3
    assert AuditEvent.objects.count() == count
    membership.refresh_from_db()
    assert membership.revoked_at is not None
