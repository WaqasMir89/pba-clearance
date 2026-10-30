import hashlib
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema
from rest_framework.exceptions import ValidationError
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.scoping import WORKSPACE_PARAMETER, WorkspaceMixin
from apps.complaints.validation import canonical_json, money
from apps.complaints.views import claim_queryset, filter_uuid
from apps.disputes import selectors, services
from apps.disputes.constants import DECLARATIONS, REASONS
from apps.disputes.models import (
    ClaimEvidence,
    DisputeCase,
    DisputeRevision,
    ObjectionDraft,
    SandboxResponseWindow,
)
from apps.disputes.serializers import (
    BreakdownSerializer,
    CaseSerializer,
    DisputeOptionsSerializer,
    DraftDetailSerializer,
    DraftInputSerializer,
    DraftListSerializer,
    EvidenceInputSerializer,
    EvidenceSerializer,
    RevisionListSerializer,
    RevisionSerializer,
    SignInputSerializer,
    WindowInputSerializer,
    WindowSerializer,
    WithdrawalInputSerializer,
)
from apps.policy.services import POLICY_READ_ROLES


def command_response(record, replayed, serializer):
    return Response(
        {**serializer(record).data, "replayed": replayed}, status=200 if replayed else 201
    )


@extend_schema(parameters=[WORKSPACE_PARAMETER])
class DisputeOptionsView(WorkspaceMixin, APIView):
    @extend_schema(responses=DisputeOptionsSerializer)
    def get(self, request):
        # Establish business scope rather than granting ordinary staff implicit access.
        claim_queryset(self.membership, request)
        return Response(
            {
                "reasons": REASONS,
                "declarations": DECLARATIONS,
                "evidence_kind": "plain_text_statement",
                "financial_effect": "none",
                "enforcement_effect": "none",
            }
        )


@extend_schema(parameters=[WORKSPACE_PARAMETER])
class WindowListView(WorkspaceMixin, ListAPIView):
    serializer_class = WindowSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return SandboxResponseWindow.objects.none()
        if (
            self.membership.role not in POLICY_READ_ROLES
            and not self.membership.organization.is_demo
        ):
            return SandboxResponseWindow.objects.none()
        return filter_uuid(
            SandboxResponseWindow.objects.all(), self.request, "cycle_id", "cycle_id"
        )

    @extend_schema(
        request=WindowInputSerializer, responses={201: WindowSerializer, 200: WindowSerializer}
    )
    def post(self, request):
        serializer = WindowInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        record, replayed = services.create_window(
            actor=request.user,
            organization_id=self.membership.organization_id,
            request_id=request.request_id,
            **serializer.validated_data,
        )
        return command_response(record, replayed, WindowSerializer)


@extend_schema(parameters=[WORKSPACE_PARAMETER])
class DraftListView(WorkspaceMixin, ListAPIView):
    serializer_class = DraftListSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return ObjectionDraft.objects.none()
        queryset = selectors.drafts_for(self.membership).select_related(
            "created_by", "signed_revision"
        )
        queryset = filter_uuid(queryset, self.request, "claim_id", "claim_id")
        queryset = filter_uuid(
            queryset,
            self.request,
            "cycle_id",
            "claim__invoice__submission__source_import__cycle_id",
        )
        return filter_uuid(queryset, self.request, "idempotency_key", "idempotency_key")

    @extend_schema(
        request=DraftInputSerializer,
        responses={201: DraftDetailSerializer, 200: DraftDetailSerializer},
    )
    def post(self, request):
        serializer = DraftInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        record, replayed = services.stage_draft(
            actor=request.user,
            organization_id=self.membership.organization_id,
            request_id=request.request_id,
            **serializer.validated_data,
        )
        return command_response(record, replayed, DraftDetailSerializer)


@extend_schema(parameters=[WORKSPACE_PARAMETER])
class DraftDetailView(WorkspaceMixin, RetrieveAPIView):
    serializer_class = DraftDetailSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return ObjectionDraft.objects.none()
        return selectors.drafts_for(self.membership).select_related(
            "created_by", "window", "signed_revision", "claim__invoice__submission__source_import"
        )


@extend_schema(parameters=[WORKSPACE_PARAMETER])
class SubmitDraftView(WorkspaceMixin, APIView):
    @extend_schema(
        request=SignInputSerializer, responses={201: RevisionSerializer, 200: RevisionSerializer}
    )
    def post(self, request, pk):
        serializer = SignInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        record, replayed = services.submit_draft(
            actor=request.user,
            organization_id=self.membership.organization_id,
            draft_id=pk,
            request_id=request.request_id,
            **serializer.validated_data,
        )
        return command_response(record, replayed, RevisionSerializer)


def case_queryset(membership, request):
    queryset = selectors.with_objections(selectors.cases_for(membership), case=True).select_related(
        "claim__invoice__channel",
        "claim__invoice__agency",
        "claim__invoice__client",
        "claim__invoice__submission__source_import__cycle",
    )
    queryset = filter_uuid(queryset, request, "claim_id", "claim_id")
    queryset = filter_uuid(
        queryset, request, "cycle_id", "claim__invoice__submission__source_import__cycle_id"
    )
    query = request.query_params.get("q", "").strip()[:120]
    return queryset.filter(claim__invoice__invoice_number__icontains=query) if query else queryset


@extend_schema(parameters=[WORKSPACE_PARAMETER])
class CaseListView(WorkspaceMixin, ListAPIView):
    serializer_class = CaseSerializer

    def get_queryset(self):
        return (
            DisputeCase.objects.none()
            if getattr(self, "swagger_fake_view", False)
            else case_queryset(self.membership, self.request)
        )


@extend_schema(parameters=[WORKSPACE_PARAMETER])
class CaseDetailView(WorkspaceMixin, RetrieveAPIView):
    serializer_class = CaseSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return DisputeCase.objects.none()
        return case_queryset(self.membership, self.request)


@extend_schema(parameters=[WORKSPACE_PARAMETER])
class WithdrawView(WorkspaceMixin, APIView):
    @extend_schema(
        request=WithdrawalInputSerializer,
        responses={201: RevisionSerializer, 200: RevisionSerializer},
    )
    def post(self, request, pk):
        serializer = WithdrawalInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        record, replayed = services.withdraw(
            actor=request.user,
            organization_id=self.membership.organization_id,
            case_id=pk,
            request_id=request.request_id,
            **serializer.validated_data,
        )
        return command_response(record, replayed, RevisionSerializer)


@extend_schema(parameters=[WORKSPACE_PARAMETER])
class RevisionListView(WorkspaceMixin, ListAPIView):
    serializer_class = RevisionListSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return DisputeRevision.objects.none()
        queryset = selectors.revisions_for(self.membership).select_related("created_by", "case")
        queryset = filter_uuid(queryset, self.request, "case_id", "case_id")
        queryset = filter_uuid(queryset, self.request, "claim_id", "case__claim_id")
        if "idempotency_key" in self.request.query_params:
            queryset = filter_uuid(
                queryset.filter(agency_id=self.membership.organization_id),
                self.request,
                "idempotency_key",
                "idempotency_key",
            )
        command_type = self.request.query_params.get("command_type")
        if command_type is not None:
            if command_type not in {"submit", "withdraw"}:
                raise ValidationError({"command_type": "Choose submit or withdraw."})
            queryset = queryset.filter(command_type=command_type)
        return (
            queryset.order_by("-version")
            if "case_id" in self.request.query_params
            else queryset.order_by("-created_at", "-id")
        )


@extend_schema(parameters=[WORKSPACE_PARAMETER])
class RevisionDetailView(WorkspaceMixin, RetrieveAPIView):
    serializer_class = RevisionSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return DisputeRevision.objects.none()
        return selectors.revisions_for(self.membership).select_related("created_by", "case")


@extend_schema(parameters=[WORKSPACE_PARAMETER])
class RevisionReceiptView(WorkspaceMixin, APIView):
    @extend_schema(responses={(200, "application/json"): OpenApiTypes.OBJECT})
    def get(self, request, pk):
        record = get_object_or_404(selectors.revisions_for(self.membership), pk=pk)
        content = canonical_json(record.receipt).encode("utf-8")
        if hashlib.sha256(content).hexdigest() != record.content_hash:
            return Response(
                {
                    "error": {
                        "code": "receipt_integrity",
                        "message": "The receipt needs an integrity review.",
                        "fields": {},
                    }
                },
                status=503,
            )
        response = HttpResponse(content, content_type="application/json; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="dispute-receipt-{record.pk}.json"'
        response["ETag"] = f'"{record.content_hash}"'
        return response


@extend_schema(parameters=[WORKSPACE_PARAMETER])
class EvidenceListView(WorkspaceMixin, ListAPIView):
    serializer_class = EvidenceSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return ClaimEvidence.objects.none()
        queryset = selectors.evidence_for(self.membership).select_related(
            "created_by", "organization"
        )
        queryset = filter_uuid(queryset, self.request, "claim_id", "claim_id")
        if "idempotency_key" in self.request.query_params:
            queryset = filter_uuid(
                queryset.filter(organization_id=self.membership.organization_id),
                self.request,
                "idempotency_key",
                "idempotency_key",
            )
        return queryset

    @extend_schema(
        request=EvidenceInputSerializer,
        responses={201: EvidenceSerializer, 200: EvidenceSerializer},
    )
    def post(self, request):
        serializer = EvidenceInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        record, replayed = services.add_evidence(
            actor=request.user,
            organization_id=self.membership.organization_id,
            request_id=request.request_id,
            **serializer.validated_data,
        )
        return command_response(record, replayed, EvidenceSerializer)


@extend_schema(parameters=[WORKSPACE_PARAMETER])
class EvidenceDetailView(WorkspaceMixin, RetrieveAPIView):
    serializer_class = EvidenceSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return ClaimEvidence.objects.none()
        return selectors.evidence_for(self.membership).select_related("created_by", "organization")


@extend_schema(
    parameters=[
        WORKSPACE_PARAMETER,
        OpenApiParameter("group_by", OpenApiTypes.STR, enum=["channel", "client", "cycle"]),
    ]
)
class ClaimBreakdownView(WorkspaceMixin, ListAPIView):
    serializer_class = BreakdownSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return []
        group = self.request.query_params.get("group_by", "channel")
        fields = {
            "channel": ("invoice__channel_id", "invoice__channel__legal_name"),
            "client": ("invoice__client_id", "invoice__client__legal_name"),
            "cycle": (
                "invoice__submission__source_import__cycle_id",
                "invoice__submission__source_import__cycle__code",
            ),
        }
        if group not in fields:
            raise ValidationError({"group_by": "Choose channel, client or cycle."})
        identifier, label = fields[group]
        queryset = selectors.with_objections(claim_queryset(self.membership, self.request))
        return (
            queryset.order_by()
            .values(identifier, label)
            .annotate(
                claim_count=Count("pk"),
                reported=Sum("reported_due"),
                disputed=Sum("disputed_amount"),
                active_objection_count=Count("pk", filter=Q(objection_state="open")),
            )
            .order_by(label, identifier)
        )

    def list(self, request, *args, **kwargs):
        group = request.query_params.get("group_by", "channel")
        fields = {
            "channel": ("invoice__channel_id", "invoice__channel__legal_name"),
            "client": ("invoice__client_id", "invoice__client__legal_name"),
            "cycle": (
                "invoice__submission__source_import__cycle_id",
                "invoice__submission__source_import__cycle__code",
            ),
        }
        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)
        identifier, label = fields[group]
        results = [
            {
                "group_id": item[identifier],
                "group_name": item[label],
                "claim_count": item["claim_count"],
                "reported_due_total": money(item["reported"] or Decimal("0.00")),
                "active_objection_count": item["active_objection_count"],
                "disputed_amount_total": money(item["disputed"] or Decimal("0.00")),
                "accepted_credit_total": None,
                "verified_settlement_total": None,
                "remaining_reportable_balance": None,
            }
            for item in page
        ]
        return self.get_paginated_response(results)
