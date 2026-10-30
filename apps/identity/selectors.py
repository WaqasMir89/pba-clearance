from uuid import UUID

from django.conf import settings
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.identity.models import Membership


def active_memberships(user):
    now = timezone.now()
    if not user.is_authenticated or not user.is_active:
        return Membership.objects.none()
    return (
        Membership.objects.filter(
            user=user, organization__is_active=True, revoked_at__isnull=True, starts_at__lte=now
        )
        .filter(Q(ends_at__isnull=True) | Q(ends_at__gt=now))
        .select_related("organization")
    )


def valid_role(membership):
    return (
        membership.role in Membership.Role.values
        and membership.role.split("_", 1)[0] == membership.organization.kind
    )


def workspace_membership(user, organization_id, *, lock=False):
    try:
        organization_id = UUID(str(organization_id))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValidationError(
            {"organization": "Choose a workspace using X-Organization-ID."}
        ) from exc
    queryset = active_memberships(user)
    if lock:
        queryset = queryset.select_for_update(of=("self",))
    membership = queryset.filter(organization_id=organization_id).first()
    if not membership or not valid_role(membership):
        raise PermissionDenied("Workspace access is unavailable.")
    return membership


def session_payload(user):
    memberships = [m for m in active_memberships(user) if valid_role(m)]
    return {
        "user": {"id": str(user.id), "username": user.username, "name": user.get_full_name()},
        "memberships": [
            {
                "id": str(m.id),
                "organization": {
                    "id": str(m.organization_id),
                    "code": m.organization.code,
                    "legal_name": m.organization.legal_name,
                    "kind": m.organization.kind,
                    "is_demo": m.organization.is_demo,
                },
                "role": m.role,
                "role_label": m.get_role_display(),
                "can_manage_registry": m.role == Membership.Role.PBA_REGISTRY,
                "can_view_audit": m.role
                in {Membership.Role.PBA_REGISTRY, Membership.Role.PBA_AUDITOR},
                "can_view_policy": m.role
                in {
                    Membership.Role.PBA_REGISTRY,
                    Membership.Role.PBA_AUDITOR,
                    Membership.Role.PBA_POLICY_PREPARER,
                },
                "can_prepare_policy": m.role == Membership.Role.PBA_POLICY_PREPARER,
                "can_stage_complaints": settings.ENVIRONMENT == "development"
                and user.is_demo
                and m.organization.is_demo
                and m.role in {Membership.Role.CHANNEL_PREPARER, Membership.Role.CHANNEL_APPROVER},
                "can_file_complaints": settings.ENVIRONMENT == "development"
                and user.is_demo
                and m.organization.is_demo
                and m.role == Membership.Role.CHANNEL_APPROVER,
                "can_view_claims": m.role
                in {
                    Membership.Role.PBA_REGISTRY,
                    Membership.Role.PBA_AUDITOR,
                    Membership.Role.CHANNEL_PREPARER,
                    Membership.Role.CHANNEL_APPROVER,
                    Membership.Role.AGENCY_PREPARER,
                    Membership.Role.AGENCY_APPROVER,
                },
            }
            for m in memberships
        ],
        "environment": settings.ENVIRONMENT,
        "enforcement_enabled": False,
    }
