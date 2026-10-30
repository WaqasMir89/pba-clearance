import base64
import binascii
import re

from rest_framework import serializers

from apps.complaints.constants import DECLARATION_VERSION, MAX_SOURCE_BYTES
from apps.complaints.models import ComplaintImport, ReportedClaim, Submission


class ImportInputSerializer(serializers.Serializer):
    cycle_id = serializers.UUIDField()
    source_filename = serializers.CharField(max_length=120)
    csv_base64 = serializers.CharField(
        source="source_bytes",
        max_length=4 * ((MAX_SOURCE_BYTES + 2) // 3),
        trim_whitespace=False,
        write_only=True,
    )
    idempotency_key = serializers.UUIDField()

    def validate_csv_base64(self, value):
        try:
            content = base64.b64decode(value, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise serializers.ValidationError("The file content is not valid base64.") from exc
        if not content or len(content) > MAX_SOURCE_BYTES:
            raise serializers.ValidationError("Choose a nonempty CSV file of at most 256 KiB.")
        return content


class OffsetDateTimeField(serializers.DateTimeField):
    def to_internal_value(self, value):
        if not isinstance(value, str) or not re.fullmatch(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}(?::[0-9]{2}(?:\.[0-9]{1,6})?)?(?:Z|[+-][0-9]{2}:[0-9]{2})",
            value,
        ):
            self.fail("invalid", format="ISO timestamp with an explicit timezone offset")
        return super().to_internal_value(value)


class FilingInputSerializer(serializers.Serializer):
    expected_preview_hash = serializers.RegexField(r"^[a-f0-9]{64}$", max_length=64)
    simulation_at = OffsetDateTimeField()
    declaration_version = serializers.ChoiceField(choices=[DECLARATION_VERSION])
    declaration_accepted = serializers.BooleanField()
    idempotency_key = serializers.UUIDField()


class IssueSerializer(serializers.Serializer):
    field = serializers.CharField()
    code = serializers.CharField()
    message = serializers.CharField()


class RowPreviewSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    number = serializers.IntegerField()
    values = serializers.DictField(child=serializers.CharField(allow_blank=True))
    canonical = serializers.DictField(allow_null=True)
    status = serializers.ChoiceField(choices=["ready", "invalid", "review", "duplicate"])
    issues = IssueSerializer(many=True)
    duplicate_of_row = serializers.IntegerField(allow_null=True)
    existing_invoice_id = serializers.UUIDField(allow_null=True)


class PreviewSerializer(serializers.Serializer):
    rows = RowPreviewSerializer(many=True)
    counts = serializers.DictField(child=serializers.IntegerField())
    ready_reported_total = serializers.CharField()
    preview_hash = serializers.CharField()
    checked_at = serializers.DateTimeField()


class ImportListSerializer(serializers.ModelSerializer):
    cycle_code = serializers.CharField(source="cycle.code", read_only=True)
    created_by = serializers.CharField(source="created_by.username", read_only=True)
    submission_id = serializers.SerializerMethodField()

    class Meta:
        model = ComplaintImport
        fields = [
            "id",
            "channel_id",
            "cycle_id",
            "cycle_code",
            "source_filename",
            "source_sha256",
            "created_at",
            "created_by",
            "row_count",
            "is_demo",
            "submission_id",
        ]

    def get_submission_id(self, obj) -> str | None:
        submission = getattr(obj, "submission", None)
        return str(submission.pk) if submission and submission.is_sealed else None


class ImportDetailSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    channel_id = serializers.UUIDField()
    cycle_id = serializers.UUIDField()
    cycle_code = serializers.CharField()
    source_filename = serializers.CharField()
    source_sha256 = serializers.CharField()
    created_at = serializers.DateTimeField()
    created_by = serializers.CharField()
    row_count = serializers.IntegerField()
    validator_version = serializers.CharField()
    is_demo = serializers.BooleanField()
    submission_id = serializers.UUIDField(allow_null=True)
    preview = PreviewSerializer(allow_null=True)
    preview_current = serializers.BooleanField()
    replayed = serializers.BooleanField(required=False)


class SubmissionSerializer(serializers.ModelSerializer):
    submitted_by = serializers.CharField(source="submitted_by.username", read_only=True)
    replayed = serializers.BooleanField(required=False, read_only=True)

    class Meta:
        model = Submission
        fields = [
            "id",
            "source_import_id",
            "channel_id",
            "submitted_by",
            "submitted_at",
            "simulation_at",
            "content_hash",
            "receipt",
            "row_count",
            "reported_total",
            "is_demo",
            "replayed",
        ]


class ClaimSerializer(serializers.ModelSerializer):
    invoice_id = serializers.UUIDField(read_only=True)
    invoice_number = serializers.CharField(source="invoice.invoice_number", read_only=True)
    invoice_date = serializers.DateField(source="invoice.invoice_date", read_only=True)
    financial_year = serializers.CharField(source="invoice.financial_year", read_only=True)
    channel_id = serializers.UUIDField(source="invoice.channel_id", read_only=True)
    channel_name = serializers.CharField(source="invoice.channel.legal_name", read_only=True)
    agency_id = serializers.UUIDField(source="invoice.agency_id", read_only=True)
    agency_name = serializers.CharField(source="invoice.agency.legal_name", read_only=True)
    client_id = serializers.UUIDField(source="invoice.client_id", read_only=True)
    client_name = serializers.CharField(source="invoice.client.legal_name", read_only=True)
    principal_amount = serializers.DecimalField(
        source="invoice.principal_amount", max_digits=18, decimal_places=2, read_only=True
    )
    gst_amount = serializers.DecimalField(
        source="invoice.gst_amount", max_digits=18, decimal_places=2, read_only=True
    )
    invoice_total = serializers.DecimalField(
        source="invoice.invoice_total", max_digits=18, decimal_places=2, read_only=True
    )
    currency = serializers.CharField(source="invoice.currency", read_only=True)
    cycle_id = serializers.UUIDField(
        source="invoice.submission.source_import.cycle_id", read_only=True
    )
    cycle_code = serializers.CharField(
        source="invoice.submission.source_import.cycle.code", read_only=True
    )
    submission_id = serializers.UUIDField(source="invoice.submission_id", read_only=True)
    submitted_at = serializers.DateTimeField(
        source="invoice.submission.submitted_at", read_only=True
    )

    class Meta:
        model = ReportedClaim
        fields = [
            "id",
            "invoice_id",
            "invoice_number",
            "invoice_date",
            "financial_year",
            "channel_id",
            "channel_name",
            "agency_id",
            "agency_name",
            "client_id",
            "client_name",
            "principal_amount",
            "gst_amount",
            "invoice_total",
            "reported_due",
            "balance_explanation",
            "currency",
            "cycle_id",
            "cycle_code",
            "submission_id",
            "submitted_at",
        ]


class ClaimSummarySerializer(serializers.Serializer):
    count = serializers.IntegerField()
    reported_due_total = serializers.CharField()
    currency = serializers.CharField()
    basis = serializers.CharField()
    is_demo = serializers.BooleanField()


class IntakeOptionsSerializer(serializers.Serializer):
    agencies = serializers.ListField(child=serializers.DictField())
    clients = serializers.ListField(child=serializers.DictField())
    client_count = serializers.IntegerField()
    client_limit = serializers.IntegerField()
    max_source_bytes = serializers.IntegerField()
    max_rows = serializers.IntegerField()
    required_headers = serializers.ListField(child=serializers.CharField())
    optional_headers = serializers.ListField(child=serializers.CharField())
    declaration = serializers.DictField()
