import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class Immutable(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise TypeError("Objection and evidence history is immutable. Create a new record.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise TypeError("Objection and evidence history cannot be deleted.")


class SandboxResponseWindow(Immutable):
    cycle = models.OneToOneField("policy.ClearanceCycle", on_delete=models.PROTECT)
    organization = models.ForeignKey("registry.Organization", on_delete=models.PROTECT)
    opens_at = models.DateTimeField()
    closes_at = models.DateTimeField()
    source_reference = models.CharField(max_length=255)
    source_sha256 = models.CharField(max_length=64)
    idempotency_key = models.UUIDField()
    request_hash = models.CharField(max_length=64)
    status = models.CharField(max_length=20, default="candidate", editable=False)
    is_demo = models.BooleanField(default=True, editable=False)

    class Meta:
        ordering = ["-opens_at", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "idempotency_key"], name="unique_response_window_command"
            ),
            models.CheckConstraint(
                condition=models.Q(closes_at__gt=models.F("opens_at")),
                name="response_window_ordered",
            ),
            models.CheckConstraint(
                condition=models.Q(is_demo=True, status="candidate"),
                name="response_window_candidate_demo",
            ),
            models.CheckConstraint(
                condition=models.Q(source_sha256__regex=r"^[a-f0-9]{64}$"),
                name="response_window_source_hash",
            ),
        ]


class ObjectionDraft(Immutable):
    claim = models.ForeignKey("complaints.ReportedClaim", on_delete=models.PROTECT)
    agency = models.ForeignKey("registry.Organization", on_delete=models.PROTECT)
    window = models.ForeignKey(SandboxResponseWindow, on_delete=models.PROTECT, null=True)
    base_version = models.PositiveIntegerField()
    disputed_amount = models.DecimalField(max_digits=18, decimal_places=2)
    reason_code = models.CharField(max_length=30)
    explanation = models.CharField(max_length=3000)
    supporting_statement = models.CharField(max_length=6000)
    source_reference = models.CharField(max_length=255, blank=True)
    claim_snapshot = models.JSONField()
    content_hash = models.CharField(max_length=64)
    idempotency_key = models.UUIDField()
    request_hash = models.CharField(max_length=64)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["agency", "idempotency_key"], name="unique_objection_draft_command"
            ),
            models.CheckConstraint(
                condition=models.Q(disputed_amount__gt=0), name="objection_draft_positive_amount"
            ),
            models.CheckConstraint(
                condition=models.Q(
                    reason_code__in=["invoice_details", "amount", "service_delivery", "other"]
                ),
                name="objection_draft_reason",
            ),
        ]


class DisputeCase(Immutable):
    claim = models.OneToOneField(
        "complaints.ReportedClaim", on_delete=models.PROTECT, related_name="dispute_case"
    )
    agency = models.ForeignKey(
        "registry.Organization", on_delete=models.PROTECT, related_name="agency_disputes"
    )
    channel = models.ForeignKey(
        "registry.Organization", on_delete=models.PROTECT, related_name="channel_disputes"
    )

    class Meta:
        ordering = ["-created_at", "-id"]


class DisputeRevision(Immutable):
    case = models.ForeignKey(DisputeCase, on_delete=models.PROTECT, related_name="revisions")
    draft = models.OneToOneField(
        ObjectionDraft, on_delete=models.PROTECT, null=True, related_name="signed_revision"
    )
    agency = models.ForeignKey("registry.Organization", on_delete=models.PROTECT)
    version = models.PositiveIntegerField()
    action = models.CharField(max_length=20)
    disputed_amount = models.DecimalField(max_digits=18, decimal_places=2)
    simulation_at = models.DateTimeField()
    command_type = models.CharField(max_length=20)
    idempotency_key = models.UUIDField()
    request_hash = models.CharField(max_length=64)
    content_hash = models.CharField(max_length=64)
    receipt = models.JSONField()

    class Meta:
        ordering = ["-version", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["case", "version"], name="unique_dispute_revision_version"
            ),
            models.UniqueConstraint(
                fields=["agency", "command_type", "idempotency_key"],
                name="unique_dispute_revision_command",
            ),
            models.CheckConstraint(
                condition=models.Q(version__gte=1), name="dispute_revision_positive_version"
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        action="withdrawn",
                        disputed_amount=0,
                        command_type="withdraw",
                        draft__isnull=True,
                    )
                    | models.Q(
                        action__in=["raised", "amended", "reopened"],
                        disputed_amount__gt=0,
                        command_type="submit",
                        draft__isnull=False,
                    )
                ),
                name="dispute_revision_action_amount",
            ),
        ]


class ClaimEvidence(Immutable):
    claim = models.ForeignKey(
        "complaints.ReportedClaim", on_delete=models.PROTECT, related_name="evidence_statements"
    )
    organization = models.ForeignKey("registry.Organization", on_delete=models.PROTECT)
    window = models.ForeignKey(SandboxResponseWindow, on_delete=models.PROTECT, null=True)
    statement = models.CharField(max_length=6000)
    source_reference = models.CharField(max_length=255, blank=True)
    simulation_at = models.DateTimeField()
    timing = models.CharField(max_length=20)
    idempotency_key = models.UUIDField()
    request_hash = models.CharField(max_length=64)
    content_hash = models.CharField(max_length=64)
    receipt = models.JSONField()

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "idempotency_key"], name="unique_claim_evidence_command"
            ),
            models.CheckConstraint(
                condition=models.Q(
                    timing__in=["before_window", "within_window", "late", "window_unknown"]
                ),
                name="claim_evidence_timing",
            ),
        ]
