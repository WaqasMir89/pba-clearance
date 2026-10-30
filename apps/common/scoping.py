from django.db import transaction
from django.http import Http404
from drf_spectacular.utils import OpenApiParameter, OpenApiTypes
from rest_framework.exceptions import NotFound, PermissionDenied

from apps.audit.models import AuditEvent
from apps.identity.selectors import workspace_membership

WORKSPACE_PARAMETER = OpenApiParameter(
    "X-Organization-ID",
    OpenApiTypes.UUID,
    OpenApiParameter.HEADER,
    required=True,
    description="A currently authorized organization membership.",
)


class WorkspaceMixin:
    """Live authorization; do not trust role/organization stored in a browser session."""

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.membership = workspace_membership(
            request.user, request.headers.get("X-Organization-ID")
        )

    def handle_exception(self, exc):
        if (
            isinstance(exc, (PermissionDenied, NotFound, Http404))
            and self.request.user.is_authenticated
        ):
            # Run after a command's transaction unwinds so the denial persists.
            with transaction.atomic():
                AuditEvent.objects.create(
                    actor=self.request.user,
                    organization_id=getattr(
                        getattr(self, "membership", None), "organization_id", None
                    ),
                    action="access.denied",
                    subject_type="identity.user",
                    subject_id=self.request.user.pk,
                    request_id=self.request.request_id,
                )
        return super().handle_exception(exc)
