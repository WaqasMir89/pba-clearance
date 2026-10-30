import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class ImmutableRecord(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise TypeError("Filing records are immutable; preserve history in a new record.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise TypeError("Filing records cannot be deleted.")


class ComplaintImport(ImmutableRecord):
    channel = models.ForeignKey("registry.Organization", on_delete=models.PROTECT)
    cycle = models.ForeignKey("policy.ClearanceCycle", on_delete=models.PROTECT)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    source_filename = models.CharField(max_length=120)
    source_bytes = models.BinaryField()
    source_sha256 = models.CharField(max_length=64)
    idempotency_key = models.UUIDField()
    request_hash = models.CharField(max_length=64)
    validator_version = models.CharField(max_length=40, default="complaint-csv-v1", editable=False)
    row_count = models.PositiveIntegerField()
    is_sealed = models.BooleanField(default=False, editable=False)
    is_demo = models.BooleanField(default=True, editable=False)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["channel", "idempotency_key"], name="unique_import_command"
            ),
            models.CheckConstraint(
                condition=models.Q(is_demo=True), name="complaint_import_demo_only"
            ),
            models.CheckConstraint(
                condition=models.Q(row_count__gte=1, row_count__lte=500), name="import_bounded_rows"
            ),
        ]


class ImportRow(ImmutableRecord):
    batch = models.ForeignKey(ComplaintImport, on_delete=models.PROTECT, related_name="rows")
    number = models.PositiveIntegerField()
    values = models.JSONField()
    parse_issues = models.JSONField(default=list)

    class Meta:
        ordering = ["number", "id"]
        constraints = [
            models.UniqueConstraint(fields=["batch", "number"], name="unique_import_source_row"),
            models.CheckConstraint(
                condition=models.Q(number__gte=2), name="import_row_after_header"
            ),
        ]


class Submission(ImmutableRecord):
    source_import = models.OneToOneField(
        ComplaintImport, on_delete=models.PROTECT, related_name="submission"
    )
    channel = models.ForeignKey("registry.Organization", on_delete=models.PROTECT)
    submitted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    submitted_at = models.DateTimeField(default=timezone.now, editable=False)
    simulation_at = models.DateTimeField()
    idempotency_key = models.UUIDField()
    request_hash = models.CharField(max_length=64)
    content_hash = models.CharField(max_length=64)
    receipt = models.JSONField()
    preview_snapshot = models.JSONField()
    row_count = models.PositiveIntegerField()
    reported_total = models.DecimalField(max_digits=21, decimal_places=2)
    is_sealed = models.BooleanField(default=False, editable=False)
    is_demo = models.BooleanField(default=True, editable=False)

    class Meta:
        ordering = ["-submitted_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["channel", "idempotency_key"], name="unique_filing_command"
            ),
            models.CheckConstraint(condition=models.Q(is_demo=True), name="submission_demo_only"),
            models.CheckConstraint(
                condition=models.Q(row_count__gte=1, row_count__lte=500),
                name="submission_bounded_rows",
            ),
            models.CheckConstraint(
                condition=models.Q(reported_total__gt=0), name="submission_positive_total"
            ),
        ]


class Invoice(ImmutableRecord):
    submission = models.ForeignKey(Submission, on_delete=models.PROTECT, related_name="invoices")
    source_row = models.OneToOneField(ImportRow, on_delete=models.PROTECT)
    channel = models.ForeignKey(
        "registry.Organization", on_delete=models.PROTECT, related_name="reported_invoices"
    )
    agency = models.ForeignKey(
        "registry.Organization", on_delete=models.PROTECT, related_name="invoices_against"
    )
    client = models.ForeignKey("registry.Client", on_delete=models.PROTECT)
    financial_year = models.CharField(max_length=9)
    invoice_number = models.CharField(max_length=120)
    normalized_number = models.CharField(max_length=240)
    comparison_key = models.CharField(max_length=240, db_index=True)
    invoice_date = models.DateField()
    broadcast_start = models.DateField()
    broadcast_end = models.DateField()
    principal_amount = models.DecimalField(max_digits=18, decimal_places=2)
    gst_amount = models.DecimalField(max_digits=18, decimal_places=2)
    invoice_total = models.DecimalField(max_digits=18, decimal_places=2)
    currency = models.CharField(max_length=3, default="PKR", editable=False)
    delivery_reference = models.CharField(max_length=255)
    invoice_delivered_on = models.DateField(null=True)
    release_order_reference = models.CharField(max_length=255, blank=True)
    source_id = models.CharField(max_length=120, blank=True)
    report_fingerprint = models.CharField(max_length=64)

    class Meta:
        ordering = ["-invoice_date", "id"]
        indexes = [
            models.Index(fields=["channel", "comparison_key"], name="invoice_duplicate_lookup")
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["channel", "agency", "financial_year", "normalized_number"],
                name="unique_reported_invoice_identity",
            ),
            models.CheckConstraint(
                condition=~models.Q(channel=models.F("agency")), name="invoice_distinct_parties"
            ),
            models.CheckConstraint(condition=models.Q(currency="PKR"), name="invoice_pkr_only"),
            models.CheckConstraint(
                condition=models.Q(principal_amount__gte=0, gst_amount__gte=0, invoice_total__gt=0),
                name="invoice_nonnegative_amounts",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    invoice_total=models.F("principal_amount") + models.F("gst_amount")
                ),
                name="invoice_exact_total",
            ),
            models.CheckConstraint(
                condition=models.Q(broadcast_end__gte=models.F("broadcast_start")),
                name="invoice_ordered_period",
            ),
        ]


class ReportedClaim(ImmutableRecord):
    invoice = models.OneToOneField(Invoice, on_delete=models.PROTECT, related_name="claim")
    reported_due = models.DecimalField(max_digits=18, decimal_places=2)
    balance_explanation = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ["-invoice__submission__submitted_at", "id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(reported_due__gt=0), name="claim_positive_reported_due"
            )
        ]
