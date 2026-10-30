import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class AuditEvent(models.Model):
    """Append-only for application writes; PostgreSQL also rejects UPDATE/DELETE."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization_id = models.UUIDField(null=True, blank=True, db_index=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name="audit_events"
    )
    action = models.CharField(max_length=100)
    subject_type = models.CharField(max_length=100)
    subject_id = models.UUIDField()
    details = models.JSONField(default=dict)
    request_id = models.UUIDField(null=True, blank=True)
    occurred_at = models.DateTimeField(default=timezone.now, editable=False, db_index=True)

    class Meta:
        ordering = ["-occurred_at", "-id"]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise TypeError("Audit events cannot be updated; record a linked correction.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise TypeError("Audit events cannot be deleted.")


class OutboxEvent(models.Model):
    """Durable intent only. No provider delivery is implemented in the foundation."""

    class State(models.TextChoices):
        PENDING = "pending", "Pending"
        DELIVERED = "delivered", "Delivered"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    audit_event = models.OneToOneField(AuditEvent, on_delete=models.PROTECT)
    topic = models.CharField(max_length=100)
    payload = models.JSONField(default=dict)
    state = models.CharField(max_length=20, choices=State.choices, default=State.PENDING)
    attempts = models.PositiveIntegerField(default=0)
    available_at = models.DateTimeField(default=timezone.now, db_index=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(state__in=["pending", "delivered", "failed"]),
                name="outbox_valid_state",
            )
        ]
