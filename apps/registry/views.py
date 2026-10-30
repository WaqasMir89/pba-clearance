from drf_spectacular.utils import extend_schema
from rest_framework.generics import ListCreateAPIView, RetrieveAPIView
from rest_framework.response import Response

from apps.common.scoping import WORKSPACE_PARAMETER, WorkspaceMixin
from apps.registry import selectors, services
from apps.registry.models import Client, Organization
from apps.registry.serializers import (
    ClientInputSerializer,
    ClientSerializer,
    OrganizationInputSerializer,
    OrganizationSerializer,
)


@extend_schema(parameters=[WORKSPACE_PARAMETER])
class OrganizationListView(WorkspaceMixin, ListCreateAPIView):
    serializer_class = OrganizationSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Organization.objects.none()
        queryset = selectors.organizations_for(self.membership)
        query = self.request.query_params.get("q", "").strip()[:200]
        return queryset.filter(legal_name__icontains=query) if query else queryset

    @extend_schema(request=OrganizationInputSerializer, responses={201: OrganizationSerializer})
    def post(self, request, *args, **kwargs):
        serializer = OrganizationInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        record = services.create_organization(
            actor=request.user,
            organization_id=self.membership.organization_id,
            request_id=request.request_id,
            **serializer.validated_data,
        )
        return Response(OrganizationSerializer(record).data, status=201)


@extend_schema(parameters=[WORKSPACE_PARAMETER])
class OrganizationDetailView(WorkspaceMixin, RetrieveAPIView):
    serializer_class = OrganizationSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Organization.objects.none()
        return selectors.organizations_for(self.membership)


@extend_schema(parameters=[WORKSPACE_PARAMETER])
class ClientListView(WorkspaceMixin, ListCreateAPIView):
    serializer_class = ClientSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Client.objects.none()
        queryset = selectors.clients_for(self.membership)
        query = self.request.query_params.get("q", "").strip()[:200]
        return queryset.filter(legal_name__icontains=query) if query else queryset

    @extend_schema(request=ClientInputSerializer, responses={201: ClientSerializer})
    def post(self, request, *args, **kwargs):
        serializer = ClientInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        record = services.create_client(
            actor=request.user,
            organization_id=self.membership.organization_id,
            request_id=request.request_id,
            **serializer.validated_data,
        )
        return Response(ClientSerializer(record).data, status=201)


@extend_schema(parameters=[WORKSPACE_PARAMETER])
class ClientDetailView(WorkspaceMixin, RetrieveAPIView):
    serializer_class = ClientSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Client.objects.none()
        return selectors.clients_for(self.membership)
