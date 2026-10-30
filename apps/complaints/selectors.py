from rest_framework.exceptions import PermissionDenied

from apps.complaints.models import ComplaintImport, ReportedClaim, Submission
from apps.identity.models import Membership
from apps.registry.selectors import PBA_READ_ROLES

CHANNEL_ROLES = {Membership.Role.CHANNEL_PREPARER, Membership.Role.CHANNEL_APPROVER}
AGENCY_ROLES = {Membership.Role.AGENCY_PREPARER, Membership.Role.AGENCY_APPROVER}


def imports_for(membership):
    if membership.role not in CHANNEL_ROLES:
        raise PermissionDenied("Only this channel's members may review its staged imports.")
    return ComplaintImport.objects.filter(channel_id=membership.organization_id, is_sealed=True)


def submissions_for(membership):
    queryset = Submission.objects.filter(is_sealed=True)
    if membership.role in PBA_READ_ROLES:
        return queryset
    if membership.role in CHANNEL_ROLES:
        return queryset.filter(channel_id=membership.organization_id)
    raise PermissionDenied("A filing receipt is available only to its channel or PBA oversight.")


def claims_for(membership):
    queryset = ReportedClaim.objects.filter(invoice__submission__is_sealed=True)
    if membership.role in PBA_READ_ROLES:
        return queryset
    if membership.role in CHANNEL_ROLES:
        return queryset.filter(invoice__channel_id=membership.organization_id)
    if membership.role in AGENCY_ROLES:
        return queryset.filter(invoice__agency_id=membership.organization_id)
    raise PermissionDenied("Reported claims require a channel, agency or PBA oversight role.")
