from django.db import connection

from apps.audit.models import AuditEvent, OutboxEvent


def record_event(*, actor, organization_id, action, subject, details=None, request_id=None):
    """Call inside the same transaction as the authorized business command."""
    if not connection.in_atomic_block:
        raise RuntimeError("Business events must be recorded inside an atomic transaction.")
    event = AuditEvent.objects.create(
        actor=actor,
        organization_id=organization_id,
        action=action,
        subject_type=subject._meta.label_lower,
        subject_id=subject.pk,
        details=details or {},
        request_id=request_id,
    )
    OutboxEvent.objects.create(
        audit_event=event,
        topic=action,
        payload={"audit_event_id": str(event.id), "subject_id": str(subject.pk), "version": 1},
    )
    return event
