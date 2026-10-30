import uuid

from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    is_demo = models.BooleanField(default=False)


class Membership(models.Model):
    class Role(models.TextChoices):
        PBA_REGISTRY = "pba_registry", "Registry officer"
        PBA_AUDITOR = "pba_auditor", "PBA auditor"
        CHANNEL_PREPARER = "channel_preparer", "Channel preparer"
        CHANNEL_APPROVER = "channel_approver", "Channel approver"
        AGENCY_PREPARER = "agency_preparer", "Agency preparer"
        AGENCY_APPROVER = "agency_approver", "Agency approver"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name="memberships")
    organization = models.ForeignKey("registry.Organization", on_delete=models.PROTECT)
    role = models.CharField(max_length=30, choices=Role.choices)
    starts_at = models.DateTimeField(default=timezone.now)
    ends_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["organization__legal_name", "id"]
        constraints = [
            models.UniqueConstraint(fields=["user", "organization"], name="unique_user_workspace"),
            models.CheckConstraint(
                condition=models.Q(ends_at__isnull=True)
                | models.Q(ends_at__gt=models.F("starts_at")),
                name="membership_positive_interval",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    role__in=[
                        "pba_registry",
                        "pba_auditor",
                        "channel_preparer",
                        "channel_approver",
                        "agency_preparer",
                        "agency_approver",
                    ]
                ),
                name="membership_valid_role",
            ),
        ]

    def clean(self):
        super().clean()
        if self.organization_id and self.role.split("_", 1)[0] != self.organization.kind:
            raise ValidationError({"role": "The role must match the organization type."})
