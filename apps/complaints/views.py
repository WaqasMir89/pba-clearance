import hashlib
from decimal import Decimal
from uuid import UUID

from django.db.models import Count, Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiTypes, extend_schema
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.scoping import WORKSPACE_PARAMETER, WorkspaceMixin
from apps.complaints import selectors, services
from apps.complaints.constants import (
    DECLARATION_TEXT,
    DECLARATION_VERSION,
    HEADERS,
    MAX_ROWS,
    MAX_SOURCE_BYTES,
    OPTIONAL_HEADERS,
    REQUIRED_HEADERS,
)
from apps.complaints.models import ComplaintImport, ReportedClaim, Submission
from apps.complaints.serializers import (
    ClaimSerializer,
    ClaimSummarySerializer,
    FilingInputSerializer,
    ImportDetailSerializer,
    ImportInputSerializer,
    ImportListSerializer,
    IntakeOptionsSerializer,
    SubmissionSerializer,
)
from apps.complaints.validation import canonical_json, money
from apps.disputes.selectors import with_objections
from apps.registry.models import Client, ClientAccess, Organization


def filter_uuid(queryset, request, parameter, lookup):
    value = request.query_params.get(parameter)
    if value is None:
        return queryset
    try:
        parsed = UUID(value)
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValidationError({parameter: "Provide a valid UUID."}) from exc
    return queryset.filter(**{lookup: parsed})


@extend_schema(parameters=[WORKSPACE_PARAMETER])
class ImportListView(WorkspaceMixin, ListAPIView):
    serializer_class = ImportListSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return ComplaintImport.objects.none()
        queryset = selectors.imports_for(self.membership).select_related(
            "cycle", "created_by", "submission"
        )
        queryset = filter_uuid(queryset, self.request, "cycle_id", "cycle_id")
        return filter_uuid(queryset, self.request, "idempotency_key", "idempotency_key")

    @extend_schema(
        request=ImportInputSerializer,
        responses={201: ImportDetailSerializer, 200: ImportDetailSerializer},
    )
    def post(self, request):
        serializer = ImportInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        batch, replayed = services.stage_import(
            actor=request.user,
            organization_id=self.membership.organization_id,
            request_id=request.request_id,
            **serializer.validated_data,
        )
        payload = services.import_detail(batch)
        payload["replayed"] = replayed
        return Response(ImportDetailSerializer(payload).data, status=200 if replayed else 201)


@extend_schema(parameters=[WORKSPACE_PARAMETER])
class ImportDetailView(WorkspaceMixin, APIView):
    @extend_schema(responses=ImportDetailSerializer)
    def get(self, request, pk):
        batch = get_object_or_404(
            selectors.imports_for(self.membership)
            .select_related("cycle__policy", "channel", "created_by")
            .prefetch_related("rows"),
            pk=pk,
        )
        return Response(ImportDetailSerializer(services.import_detail(batch)).data)


@extend_schema(parameters=[WORKSPACE_PARAMETER])
class FileImportView(WorkspaceMixin, APIView):
    @extend_schema(
        request=FilingInputSerializer,
        responses={201: SubmissionSerializer, 200: SubmissionSerializer},
    )
    def post(self, request, pk):
        serializer = FilingInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        submission, replayed = services.file_import(
            actor=request.user,
            organization_id=self.membership.organization_id,
            import_id=pk,
            request_id=request.request_id,
            **serializer.validated_data,
        )
        result = dict(SubmissionSerializer(submission).data)
        result["replayed"] = replayed
        return Response(result, status=200 if replayed else 201)


@extend_schema(parameters=[WORKSPACE_PARAMETER])
class SubmissionDetailView(WorkspaceMixin, RetrieveAPIView):
    serializer_class = SubmissionSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Submission.objects.none()
        return selectors.submissions_for(self.membership).select_related("submitted_by")


@extend_schema(parameters=[WORKSPACE_PARAMETER])
class ReceiptDownloadView(WorkspaceMixin, APIView):
    @extend_schema(responses={(200, "application/json"): OpenApiTypes.OBJECT})
    def get(self, request, pk):
        submission = get_object_or_404(selectors.submissions_for(self.membership), pk=pk)
        content = canonical_json(submission.receipt).encode("utf-8")
        if hashlib.sha256(content).hexdigest() != submission.content_hash:
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
        response["Content-Disposition"] = (
            f'attachment; filename="complaint-receipt-{submission.pk}.json"'
        )
        response["ETag"] = f'"{submission.content_hash}"'
        return response


def claim_queryset(membership, request):
    queryset = selectors.claims_for(membership).select_related(
        "invoice__channel",
        "invoice__agency",
        "invoice__client",
        "invoice__submission__source_import__cycle",
    )
    queryset = filter_uuid(
        queryset, request, "cycle_id", "invoice__submission__source_import__cycle_id"
    )
    queryset = filter_uuid(queryset, request, "channel_id", "invoice__channel_id")
    queryset = filter_uuid(queryset, request, "client_id", "invoice__client_id")
    queryset = with_objections(queryset)
    query = request.query_params.get("q", "").strip()[:120]
    return queryset.filter(invoice__invoice_number__icontains=query) if query else queryset


@extend_schema(parameters=[WORKSPACE_PARAMETER])
class ClaimListView(WorkspaceMixin, ListAPIView):
    serializer_class = ClaimSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return ReportedClaim.objects.none()
        return claim_queryset(self.membership, self.request)


@extend_schema(parameters=[WORKSPACE_PARAMETER])
class ClaimDetailView(WorkspaceMixin, RetrieveAPIView):
    serializer_class = ClaimSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return ReportedClaim.objects.none()
        return claim_queryset(self.membership, self.request)


@extend_schema(parameters=[WORKSPACE_PARAMETER])
class ClaimSummaryView(WorkspaceMixin, APIView):
    @extend_schema(responses=ClaimSummarySerializer)
    def get(self, request):
        queryset = claim_queryset(self.membership, request)
        stats = queryset.aggregate(
            count=Count("pk"),
            reported=Sum("reported_due"),
            disputed=Sum("disputed_amount"),
            active=Count("pk", filter=Q(objection_state="open")),
        )
        return Response(
            {
                "count": stats["count"],
                "reported_due_total": money(stats["reported"] or Decimal("0.00")),
                "disputed_amount_total": money(stats["disputed"] or Decimal("0.00")),
                "active_objection_count": stats["active"],
                "accepted_credit_total": None,
                "verified_settlement_total": None,
                "remaining_reportable_balance": None,
                "financial_effect": "none",
                "enforcement_effect": "none",
                "currency": "PKR",
                "basis": "reported_only",
                "is_demo": True,
            }
        )


class TemplateView(APIView):
    @extend_schema(responses={(200, "text/csv"): OpenApiTypes.BINARY})
    def get(self, request):
        response = HttpResponse(",".join(HEADERS) + "\r\n", content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="complaint-import-template.csv"'
        return response


@extend_schema(parameters=[WORKSPACE_PARAMETER])
class IntakeOptionsView(WorkspaceMixin, APIView):
    @extend_schema(responses=IntakeOptionsSerializer)
    def get(self, request):
        if (
            self.membership.role not in selectors.CHANNEL_ROLES
            or not self.membership.organization.is_demo
        ):
            raise PermissionDenied("A fictional channel workspace is required for intake.")
        queryset = Client.objects.filter(
            is_demo=True, access_grants__organization_id=self.membership.organization_id
        ).distinct()
        query = request.query_params.get("q", "").strip()[:120]
        if query:
            queryset = queryset.filter(Q(code__icontains=query) | Q(legal_name__icontains=query))
        client_count = queryset.count()
        clients = list(queryset.order_by("legal_name", "id")[:100])
        grants = list(
            ClientAccess.objects.filter(
                client__in=clients,
                organization__kind="agency",
                organization__is_demo=True,
                organization__is_active=True,
            ).values_list("client_id", "organization_id")
        )
        agencies = list(
            Organization.objects.filter(pk__in={org_id for _, org_id in grants}).order_by(
                "legal_name", "id"
            )
        )
        return Response(
            {
                "clients": [
                    {
                        "id": str(c.pk),
                        "code": c.code,
                        "legal_name": c.legal_name,
                        "agency_ids": [
                            str(org_id) for client_id, org_id in grants if client_id == c.pk
                        ],
                    }
                    for c in clients
                ],
                "client_count": client_count,
                "client_limit": 100,
                "agencies": [
                    {"id": str(a.pk), "code": a.code, "legal_name": a.legal_name} for a in agencies
                ],
                "max_source_bytes": MAX_SOURCE_BYTES,
                "max_rows": MAX_ROWS,
                "required_headers": list(REQUIRED_HEADERS),
                "optional_headers": list(OPTIONAL_HEADERS),
                "declaration": {"version": DECLARATION_VERSION, "text": DECLARATION_TEXT},
            }
        )
