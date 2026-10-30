from drf_spectacular.utils import extend_schema
from rest_framework.exceptions import PermissionDenied
from rest_framework.generics import ListCreateAPIView
from rest_framework.response import Response

from apps.common.scoping import WORKSPACE_PARAMETER, WorkspaceMixin
from apps.policy import services
from apps.policy.models import ClearanceCycle, PolicyVersion
from apps.policy.serializers import (
    CycleInputSerializer,
    CycleSerializer,
    PolicyInputSerializer,
    PolicySerializer,
)


@extend_schema(parameters=[WORKSPACE_PARAMETER])
class PolicyListView(WorkspaceMixin, ListCreateAPIView):
    serializer_class = PolicySerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return PolicyVersion.objects.none()
        if self.membership.role not in services.POLICY_READ_ROLES:
            raise PermissionDenied("Candidate policies require a PBA policy workspace.")
        return PolicyVersion.objects.all()

    @extend_schema(request=PolicyInputSerializer, responses={201: PolicySerializer})
    def post(self, request, *args, **kwargs):
        serializer = PolicyInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        policy = services.create_candidate_policy(
            actor=request.user,
            organization_id=self.membership.organization_id,
            request_id=request.request_id,
            **serializer.validated_data,
        )
        return Response(PolicySerializer(policy).data, status=201)


@extend_schema(parameters=[WORKSPACE_PARAMETER])
class CycleListView(WorkspaceMixin, ListCreateAPIView):
    serializer_class = CycleSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return ClearanceCycle.objects.none()
        queryset = (
            ClearanceCycle.objects.filter(is_sealed=True)
            .select_related("policy")
            .prefetch_related("milestones")
        )
        if self.membership.role in services.POLICY_READ_ROLES:
            return queryset
        if self.membership.organization.is_demo:
            return queryset.filter(policy__is_demo=True)
        return queryset.none()

    @extend_schema(request=CycleInputSerializer, responses={201: CycleSerializer})
    def post(self, request, *args, **kwargs):
        serializer = CycleInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cycle = services.create_candidate_cycle(
            actor=request.user,
            organization_id=self.membership.organization_id,
            request_id=request.request_id,
            **serializer.validated_data,
        )
        return Response(CycleSerializer(cycle).data, status=201)
