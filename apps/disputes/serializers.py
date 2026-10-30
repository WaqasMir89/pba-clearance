from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.complaints.serializers import OffsetDateTimeField
from apps.disputes import services, validation
from apps.disputes.constants import REASONS
from apps.disputes.models import (
    ClaimEvidence,
    DisputeCase,
    DisputeRevision,
    ObjectionDraft,
    SandboxResponseWindow,
)


@extend_schema_field({"type": "string", "pattern": "^[0-9]{1,16}(\\.[0-9]{1,2})?$"})
class MoneyInput(serializers.Field):
    def to_internal_value(self, data):
        return validation.amount(data)

    def to_representation(self, value):
        return str(value)


class WindowInputSerializer(serializers.Serializer):
    cycle_id = serializers.UUIDField()
    opens_at = OffsetDateTimeField()
    closes_at = OffsetDateTimeField()
    source_reference = serializers.CharField(max_length=255)
    source_sha256 = serializers.RegexField(r"^[a-f0-9]{64}$", max_length=64)
    idempotency_key = serializers.UUIDField()


class WindowSerializer(serializers.ModelSerializer):
    class Meta:
        model = SandboxResponseWindow
        fields = [
            "id",
            "cycle_id",
            "opens_at",
            "closes_at",
            "source_reference",
            "source_sha256",
            "status",
            "is_demo",
            "created_at",
        ]


class DraftInputSerializer(serializers.Serializer):
    claim_id = serializers.UUIDField()
    expected_case_version = serializers.IntegerField(min_value=0, max_value=2147483646)
    disputed_amount = MoneyInput()
    reason_code = serializers.ChoiceField(choices=REASONS)
    explanation = serializers.CharField(max_length=3000)
    supporting_statement = serializers.CharField(max_length=6000)
    source_reference = serializers.CharField(max_length=255, allow_blank=True, default="")
    idempotency_key = serializers.UUIDField()


class SignInputSerializer(serializers.Serializer):
    expected_preview_hash = serializers.RegexField(r"^[a-f0-9]{64}$", max_length=64)
    simulation_at = OffsetDateTimeField()
    declaration_version = serializers.CharField(max_length=60)
    declaration_accepted = serializers.BooleanField()
    idempotency_key = serializers.UUIDField()


class WithdrawalInputSerializer(serializers.Serializer):
    expected_case_version = serializers.IntegerField(min_value=1, max_value=2147483646)
    reason = serializers.CharField(max_length=3000)
    simulation_at = OffsetDateTimeField()
    declaration_version = serializers.CharField(max_length=60)
    declaration_accepted = serializers.BooleanField()
    idempotency_key = serializers.UUIDField()


class EvidenceInputSerializer(serializers.Serializer):
    claim_id = serializers.UUIDField()
    statement = serializers.CharField(max_length=6000)
    source_reference = serializers.CharField(max_length=255, allow_blank=True, default="")
    simulation_at = OffsetDateTimeField()
    declaration_version = serializers.CharField(max_length=60)
    declaration_accepted = serializers.BooleanField()
    idempotency_key = serializers.UUIDField()


class DraftListSerializer(serializers.ModelSerializer):
    created_by = serializers.CharField(source="created_by.username", read_only=True)
    submission_id = serializers.SerializerMethodField()

    class Meta:
        model = ObjectionDraft
        fields = [
            "id",
            "claim_id",
            "agency_id",
            "base_version",
            "disputed_amount",
            "reason_code",
            "claim_snapshot",
            "content_hash",
            "created_by",
            "created_at",
            "submission_id",
        ]

    def get_submission_id(self, obj) -> str | None:
        revision = getattr(obj, "signed_revision", None)
        return str(revision.pk) if revision else None


class DraftDetailSerializer(DraftListSerializer):
    preview = serializers.SerializerMethodField()

    class Meta(DraftListSerializer.Meta):
        fields = DraftListSerializer.Meta.fields + [
            "explanation",
            "supporting_statement",
            "source_reference",
            "preview",
        ]

    def get_preview(self, obj) -> dict:
        return services.draft_preview(obj)


class CaseSerializer(serializers.ModelSerializer):
    invoice_number = serializers.CharField(source="claim.invoice.invoice_number", read_only=True)
    channel_name = serializers.CharField(source="claim.invoice.channel.legal_name", read_only=True)
    agency_name = serializers.CharField(source="claim.invoice.agency.legal_name", read_only=True)
    client_name = serializers.CharField(source="claim.invoice.client.legal_name", read_only=True)
    cycle_id = serializers.UUIDField(
        source="claim.invoice.submission.source_import.cycle_id", read_only=True
    )
    cycle_code = serializers.CharField(
        source="claim.invoice.submission.source_import.cycle.code", read_only=True
    )
    reported_due = serializers.DecimalField(
        source="claim.reported_due", max_digits=18, decimal_places=2, read_only=True
    )
    current_version = serializers.IntegerField(source="objection_version", read_only=True)
    latest_revision_id = serializers.UUIDField(source="objection_revision_id", read_only=True)
    state = serializers.CharField(source="objection_state", read_only=True)
    current_disputed_amount = serializers.DecimalField(
        source="disputed_amount", max_digits=18, decimal_places=2, read_only=True
    )

    class Meta:
        model = DisputeCase
        fields = [
            "id",
            "claim_id",
            "agency_id",
            "channel_id",
            "invoice_number",
            "channel_name",
            "agency_name",
            "client_name",
            "cycle_id",
            "cycle_code",
            "reported_due",
            "current_version",
            "latest_revision_id",
            "state",
            "current_disputed_amount",
            "created_at",
        ]


class RevisionSerializer(serializers.ModelSerializer):
    claim_id = serializers.UUIDField(source="case.claim_id", read_only=True)
    created_by = serializers.CharField(source="created_by.username", read_only=True)

    class Meta:
        model = DisputeRevision
        fields = [
            "id",
            "case_id",
            "claim_id",
            "agency_id",
            "version",
            "action",
            "disputed_amount",
            "simulation_at",
            "command_type",
            "content_hash",
            "created_by",
            "created_at",
            "receipt",
        ]


class RevisionListSerializer(RevisionSerializer):
    class Meta(RevisionSerializer.Meta):
        fields = [field for field in RevisionSerializer.Meta.fields if field != "receipt"]


class EvidenceSerializer(serializers.ModelSerializer):
    created_by = serializers.CharField(source="created_by.username", read_only=True)
    organization_name = serializers.CharField(source="organization.legal_name", read_only=True)

    class Meta:
        model = ClaimEvidence
        fields = [
            "id",
            "claim_id",
            "organization_id",
            "organization_name",
            "statement",
            "source_reference",
            "simulation_at",
            "timing",
            "content_hash",
            "created_by",
            "created_at",
            "receipt",
        ]


class DisputeOptionsSerializer(serializers.Serializer):
    reasons = serializers.DictField(child=serializers.CharField())
    declarations = serializers.DictField()
    evidence_kind = serializers.CharField()
    financial_effect = serializers.CharField()
    enforcement_effect = serializers.CharField()


class BreakdownSerializer(serializers.Serializer):
    group_id = serializers.UUIDField()
    group_name = serializers.CharField()
    claim_count = serializers.IntegerField()
    reported_due_total = serializers.CharField()
    active_objection_count = serializers.IntegerField()
    disputed_amount_total = serializers.CharField()
    accepted_credit_total = serializers.CharField(allow_null=True)
    verified_settlement_total = serializers.CharField(allow_null=True)
    remaining_reportable_balance = serializers.CharField(allow_null=True)
