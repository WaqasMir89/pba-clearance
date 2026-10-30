import uuid
from unittest.mock import patch

import pytest
from django.db import DatabaseError, connection, transaction
from django.test import Client

from apps.audit.models import AuditEvent, OutboxEvent
from apps.audit.services import record_event
from apps.identity.models import User


def test_liveness_is_stateless():
    response = Client().get("/health/live/", HTTP_X_REQUEST_ID="untrusted text")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert uuid.UUID(response["X-Request-ID"])


def test_request_id_is_preserved():
    request_id = str(uuid.uuid4())
    response = Client().get("/health/live/", HTTP_X_REQUEST_ID=request_id)
    assert response["X-Request-ID"] == request_id


@pytest.mark.django_db
def test_readiness_checks_postgresql():
    assert connection.vendor == "postgresql"
    with connection.cursor() as cursor:
        cursor.execute("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname=current_user")
        assert cursor.fetchone() == (False, False)
    assert Client().get("/health/ready/").json() == {"status": "ready"}


def test_readiness_failure_does_not_leak_connection_details():
    with patch("apps.common.views.connection.cursor", side_effect=DatabaseError("secret")):
        response = Client().get("/health/ready/")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}


@pytest.mark.django_db
def test_schema_requires_a_named_session():
    response = Client().get("/api/v1/schema/")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "not_authenticated"
    assert response["Cache-Control"] == "no-store, private"


@pytest.mark.django_db(transaction=True)
def test_event_service_rejects_non_atomic_call():
    user = User.objects.create_user(username="fictional")
    with pytest.raises(RuntimeError, match="atomic"):
        record_event(actor=user, organization_id=None, action="example", subject=user)
    assert not AuditEvent.objects.exists()
    assert not OutboxEvent.objects.exists()


@pytest.mark.django_db
def test_business_write_audit_and_outbox_rollback_together():
    with pytest.raises(ValueError), transaction.atomic():
        user = User.objects.create_user(username="rollback")
        record_event(actor=user, organization_id=None, action="example", subject=user)
        raise ValueError("abort command")
    assert not User.objects.filter(username="rollback").exists()
    assert not AuditEvent.objects.exists()
    assert not OutboxEvent.objects.exists()


@pytest.mark.django_db
def test_audit_and_pending_intent_commit_together():
    user = User.objects.create_user(username="example")
    with transaction.atomic():
        event = record_event(actor=user, organization_id=None, action="example", subject=user)
    assert event.actor_id == user.id
    assert event.outboxevent.state == "pending"
    assert event.outboxevent.payload["subject_id"] == str(user.id)


@pytest.mark.django_db
@pytest.mark.parametrize("mutation", ["update", "delete", "raw_update", "raw_delete"])
def test_database_rejects_audit_mutation(mutation):
    event = AuditEvent.objects.create(
        action="example", subject_type="test", subject_id=uuid.uuid4()
    )
    with pytest.raises(DatabaseError), transaction.atomic():
        if mutation == "update":
            AuditEvent.objects.filter(pk=event.pk).update(action="tampered")
        elif mutation == "delete":
            AuditEvent.objects.filter(pk=event.pk).delete()
        else:
            with connection.cursor() as cursor:
                if mutation == "raw_update":
                    cursor.execute(
                        "UPDATE audit_auditevent SET action='tampered' WHERE id=%s", [event.id]
                    )
                else:
                    cursor.execute("DELETE FROM audit_auditevent WHERE id=%s", [event.id])
    event.refresh_from_db()
    assert event.action == "example"
