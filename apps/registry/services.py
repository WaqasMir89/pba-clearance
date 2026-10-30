from django.conf import settings
from django.db import IntegrityError, transaction
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.audit.services import record_event
from apps.identity.models import Membership
from apps.identity.selectors import workspace_membership
from apps.registry.models import Client, ClientAccess, Organization


def require_registry_officer(actor, organization_id):
    if settings.ENVIRONMENT != "development":
        raise PermissionDenied("Registry changes are not enabled in this environment.")
    membership = workspace_membership(actor, organization_id, lock=True)
    if membership.role != Membership.Role.PBA_REGISTRY:
        raise PermissionDenied("A PBA registry officer must create registry records.")
    return membership


@transaction.atomic
def create_organization(
    *, actor, organization_id, legal_name, code, kind, request_id=None, is_demo=False
):
    require_registry_officer(actor, organization_id)
    record = Organization(
        legal_name=legal_name.strip(),
        code=code.strip().lower(),
        kind=kind,
        is_demo=is_demo,
        created_by=actor,
    )
    record.full_clean()
    try:
        with transaction.atomic():
            record.save(force_insert=True)
    except IntegrityError as exc:
        raise ValidationError({"code": "This organization identifier already exists."}) from exc
    record_event(
        actor=actor,
        organization_id=organization_id,
        action="registry.organization_created",
        subject=record,
        details={"code": record.code, "kind": record.kind},
        request_id=request_id,
    )
    return record


@transaction.atomic
def create_client(
    *, actor, organization_id, legal_name, code, participant_ids, request_id=None, is_demo=False
):
    require_registry_officer(actor, organization_id)
    participants = list(Organization.objects.filter(pk__in=participant_ids, is_active=True))
    if not participants or len(participants) != len(set(participant_ids)):
        raise ValidationError(
            {"participant_ids": "Choose existing, active participating organizations."}
        )
    if any(p.kind == Organization.Kind.PBA for p in participants):
        raise ValidationError({"participant_ids": "Choose channel or agency workspaces."})
    record = Client(
        legal_name=legal_name.strip(), code=code.strip().lower(), created_by=actor, is_demo=is_demo
    )
    record.full_clean()
    try:
        with transaction.atomic():
            record.save(force_insert=True)
    except IntegrityError as exc:
        raise ValidationError({"code": "This client identifier already exists."}) from exc
    ClientAccess.objects.bulk_create(
        [ClientAccess(client=record, organization=p) for p in participants]
    )
    record_event(
        actor=actor,
        organization_id=organization_id,
        action="registry.client_created",
        subject=record,
        details={"code": record.code, "participant_ids": sorted(str(p.id) for p in participants)},
        request_id=request_id,
    )
    return record
