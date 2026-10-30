from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.generics import ListAPIView

from apps.audit.models import AuditEvent
from apps.common.scoping import WORKSPACE_PARAMETER, WorkspaceMixin
from apps.registry.selectors import PBA_READ_ROLES


class AuditSerializer(serializers.ModelSerializer):
    actor_name = serializers.CharField(source="actor.username", default="System", read_only=True)

    class Meta:
        model = AuditEvent
        fields = [
            "id",
            "action",
            "subject_type",
            "subject_id",
            "actor_name",
            "request_id",
            "occurred_at",
        ]


@extend_schema(parameters=[WORKSPACE_PARAMETER])
class AuditListView(WorkspaceMixin, ListAPIView):
    serializer_class = AuditSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return AuditEvent.objects.none()
        if self.membership.role not in PBA_READ_ROLES:
            raise PermissionDenied("Audit history requires a PBA oversight role.")
        return AuditEvent.objects.filter(
            organization_id=self.membership.organization_id
        ).select_related("actor")
