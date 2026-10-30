import time
from datetime import timedelta
from uuid import uuid4

import pytest
from django.db import DatabaseError, connection, transaction
from django.utils import timezone

from apps.complaints.models import ComplaintImport, ImportRow, Invoice, ReportedClaim, Submission
from apps.identity.models import Membership
from tests.complaints_helpers import file, row, stage

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("record_type", ["import", "row", "invoice", "claim", "submission"])
@pytest.mark.parametrize("operation", ["update", "delete"])
def test_database_rejects_changes_to_filing_history(intake, record_type, operation):
    batch, _ = stage(intake)
    submission, _ = file(intake, batch)
    records = {
        "import": batch,
        "row": batch.rows.first(),
        "invoice": Invoice.objects.get(),
        "claim": ReportedClaim.objects.get(),
        "submission": submission,
    }
    record = records[record_type]
    table = connection.ops.quote_name(record._meta.db_table)
    with pytest.raises(DatabaseError), transaction.atomic():
        with connection.cursor() as cursor:
            if operation == "update":
                cursor.execute(f"UPDATE {table} SET id=id WHERE id=%s", [record.pk])
            else:
                cursor.execute(f"DELETE FROM {table} WHERE id=%s", [record.pk])
    assert type(record).objects.filter(pk=record.pk).exists()


def test_sealed_import_cannot_gain_a_late_row(intake):
    batch, _ = stage(intake)
    with pytest.raises(DatabaseError, match="append"), transaction.atomic():
        ImportRow.objects.create(batch=batch, number=100, values=row())
    assert batch.rows.count() == 1


def test_sealed_receipt_cannot_gain_a_late_invoice(intake):
    batch, _ = stage(intake, [row(), row(invoice_number="INV/002", invoice_total="1180.01")])
    submission, _ = file(intake, batch)
    original = Invoice.objects.get()
    values = {
        field.attname: getattr(original, field.attname)
        for field in Invoice._meta.concrete_fields
        if not field.primary_key
    }
    values.update(
        source_row_id=batch.rows.last().id,
        normalized_number="late",
        invoice_number="late",
        comparison_key="late",
    )
    with pytest.raises(DatabaseError, match="unsealed"), transaction.atomic():
        Invoice.objects.create(**values)
    assert submission.invoices.count() == 1


def test_sealed_receipt_cannot_gain_a_late_claim(intake):
    batch, _ = stage(intake)
    file(intake, batch)
    with pytest.raises(DatabaseError, match="unsealed"), transaction.atomic():
        ReportedClaim.objects.create(invoice=Invoice.objects.get(), reported_due="1.00")


def raw_submission_values(intake, batch):
    return {
        "source_import": batch,
        "channel": intake.channel,
        "submitted_by": intake.checker,
        "simulation_at": timezone.now(),
        "idempotency_key": uuid4(),
        "request_hash": "a" * 64,
        "content_hash": "b" * 64,
        "receipt": {"row_count": 1, "reported_total": "1.00", "preview_hash": "c" * 64},
        "preview_snapshot": {"preview_hash": "c" * 64},
        "row_count": 1,
        "reported_total": "1.00",
    }


def test_database_cannot_create_a_presealed_filing(intake):
    batch, _ = stage(intake)
    with pytest.raises(DatabaseError), transaction.atomic():
        Submission.objects.create(**raw_submission_values(intake, batch), is_sealed=True)


def test_database_cannot_seal_a_receipt_with_missing_claims(intake):
    batch, _ = stage(intake)
    submission = Submission.objects.create(**raw_submission_values(intake, batch))
    with pytest.raises(DatabaseError, match="inconsistent totals"), transaction.atomic():
        Submission.objects.filter(pk=submission.pk).update(is_sealed=True)
    submission.refresh_from_db()
    assert not submission.is_sealed


def test_database_uses_live_expiry_after_transaction_start(intake):
    batch, _ = stage(intake)
    now = timezone.now()
    Membership.objects.filter(user=intake.checker, organization=intake.channel).update(
        starts_at=now - timedelta(days=1), ends_at=now + timedelta(milliseconds=150)
    )
    time.sleep(0.2)
    with pytest.raises(DatabaseError, match="current sandbox"), transaction.atomic():
        Submission.objects.create(**raw_submission_values(intake, batch))


def test_database_checks_source_size_and_original_byte_digest(intake):
    batch, _ = stage(intake)
    values = {
        field.attname: getattr(batch, field.attname)
        for field in ComplaintImport._meta.concrete_fields
        if not field.primary_key
    }
    values.update(is_sealed=False, idempotency_key=uuid4(), source_sha256="0" * 64)
    with pytest.raises(DatabaseError, match="source_hash"), transaction.atomic():
        ComplaintImport.objects.create(**values)
