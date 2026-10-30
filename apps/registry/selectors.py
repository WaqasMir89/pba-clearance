from apps.identity.models import Membership
from apps.registry.models import Client, Organization

PBA_READ_ROLES = {Membership.Role.PBA_REGISTRY, Membership.Role.PBA_AUDITOR}


def organizations_for(membership):
    if membership.role in PBA_READ_ROLES:
        return Organization.objects.all()
    return Organization.objects.filter(pk=membership.organization_id)


def clients_for(membership):
    queryset = Client.objects.all()
    if membership.role not in PBA_READ_ROLES:
        queryset = queryset.filter(access_grants__organization_id=membership.organization_id)
    return queryset.distinct()
