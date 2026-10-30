import uuid

from django.conf import settings
from django.db import models
from django.db.models.functions import Trim
from django.utils import timezone


class Organization(models.Model):
    class Kind(models.TextChoices):
        PBA = "pba", "PBA operations"
        CHANNEL = "channel", "Channel"
        AGENCY = "agency", "Agency"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.SlugField(max_length=40, unique=True)
    legal_name = models.CharField(max_length=200)
    kind = models.CharField(max_length=20, choices=Kind.choices)
    is_active = models.BooleanField(default=True)
    is_demo = models.BooleanField(default=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        ordering = ["legal_name", "id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(kind__in=["pba", "channel", "agency"]),
                name="organization_valid_kind",
            ),
            models.CheckConstraint(
                condition=~models.Q(legal_name="") & ~models.Q(legal_name__regex=r"^\s*$"),
                name="organization_nonempty_name",
            ),
            models.UniqueConstraint(
                fields=["kind"], condition=models.Q(kind="pba"), name="single_pba_organization"
            ),
            models.UniqueConstraint(Trim("code"), name="organization_trimmed_code"),
        ]


class Client(models.Model):
    """Legal registry entry. Visibility grants are not approved agency appointments."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.SlugField(max_length=40, unique=True)
    legal_name = models.CharField(max_length=200)
    is_demo = models.BooleanField(default=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        ordering = ["legal_name", "id"]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(legal_name="") & ~models.Q(legal_name__regex=r"^\s*$"),
                name="client_nonempty_name",
            )
        ]


class ClientAccess(models.Model):
    client = models.ForeignKey(Client, on_delete=models.PROTECT, related_name="access_grants")
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["client", "organization"], name="unique_client_access")
        ]
