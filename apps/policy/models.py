import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone


class Snapshot(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise TypeError("Create a new candidate snapshot instead of changing history.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise TypeError("Candidate snapshots cannot be deleted.")


class PolicyVersion(Snapshot):
    code = models.SlugField(max_length=40)
    version = models.PositiveIntegerField()
    title = models.CharField(max_length=200)
    source_reference = models.CharField(max_length=255)
    source_sha256 = models.CharField(max_length=64, validators=[RegexValidator(r"^[a-f0-9]{64}$")])
    effective_from = models.DateField()
    effective_until = models.DateField(null=True, blank=True)
    is_demo = models.BooleanField(default=False)
    status = models.CharField(max_length=20, default="candidate", editable=False)

    def clean(self):
        super().clean()
        if (
            self.effective_until
            and self.effective_from
            and self.effective_until <= self.effective_from
        ):
            raise ValidationError({"effective_until": "The end date must be after the start date."})

    class Meta:
        ordering = ["code", "-version"]
        constraints = [
            models.UniqueConstraint(fields=["code", "version"], name="unique_policy_version"),
            models.CheckConstraint(
                condition=models.Q(version__gte=1), name="policy_positive_version"
            ),
            models.CheckConstraint(
                condition=models.Q(status="candidate"), name="policy_candidate_only"
            ),
            models.CheckConstraint(
                condition=models.Q(source_sha256__regex=r"^[a-f0-9]{64}$"),
                name="policy_valid_source_hash",
            ),
            models.CheckConstraint(
                condition=models.Q(effective_until__isnull=True)
                | models.Q(effective_until__gt=models.F("effective_from")),
                name="policy_positive_interval",
            ),
        ]


class ClearanceCycle(Snapshot):
    code = models.SlugField(max_length=60, unique=True)
    title = models.CharField(max_length=200)
    policy = models.ForeignKey(PolicyVersion, on_delete=models.PROTECT, related_name="cycles")
    broadcast_start = models.DateField()
    broadcast_end = models.DateField()
    is_sealed = models.BooleanField(default=False, editable=False)

    def clean(self):
        super().clean()
        if (
            self.broadcast_start
            and self.broadcast_end
            and self.broadcast_end < self.broadcast_start
        ):
            raise ValidationError(
                {"broadcast_end": "The broadcast end must follow the start date."}
            )

    class Meta:
        ordering = ["-broadcast_start", "code"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(broadcast_end__gte=models.F("broadcast_start")),
                name="cycle_valid_broadcast_period",
            )
        ]


class Milestone(models.Model):
    class Code(models.TextChoices):
        COMPLAINT_OPEN = "complaint_open", "Complaint filing opens"
        COMPLAINT_CLOSE = "complaint_close", "Complaint filing closes"
        CIRCULATION = "circulation", "Agency circulation"
        PAYMENT_CUTOFF = "payment_cutoff", "Payment cutoff"
        COMMITTEE = "committee", "Committee review"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cycle = models.ForeignKey(ClearanceCycle, on_delete=models.PROTECT, related_name="milestones")
    code = models.CharField(max_length=30, choices=Code.choices)
    local_date = models.DateField()
    local_time = models.TimeField()
    timezone_name = models.CharField(max_length=40, default="Asia/Karachi", editable=False)
    occurs_at = models.DateTimeField()

    class Meta:
        ordering = ["occurs_at", "code"]
        constraints = [
            models.UniqueConstraint(fields=["cycle", "code"], name="unique_cycle_milestone"),
            models.CheckConstraint(
                condition=models.Q(timezone_name="Asia/Karachi"), name="milestone_pk_timezone"
            ),
            models.CheckConstraint(
                condition=models.Q(
                    code__in=[
                        "complaint_open",
                        "complaint_close",
                        "circulation",
                        "payment_cutoff",
                        "committee",
                    ]
                ),
                name="milestone_valid_code",
            ),
        ]
