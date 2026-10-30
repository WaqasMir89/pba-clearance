import hashlib
from decimal import Decimal

import pytest
from rest_framework.exceptions import ValidationError

from apps.complaints.constants import HEADERS, MAX_SOURCE_BYTES
from apps.complaints.models import ComplaintImport, Invoice, ReportedClaim
from apps.complaints.services import preview_import
from apps.complaints.validation import parse_csv
from apps.registry.models import ClientAccess, Organization
from tests.complaints_helpers import file, row, source_csv, stage


@pytest.mark.parametrize(
    "source",
    [
        b"",
        b"agency_code\nvalue\n",
        b"\xff\xfe",
        b"x" * (MAX_SOURCE_BYTES + 1),
        (",".join(HEADERS) + "\r\n").encode(),
        source_csv([row()]).replace(b"agency_code", b"agency_code,agency_code", 1),
        source_csv([row()]).replace(b"source_id", b"unexpected_column", 1),
        source_csv([row()]) + b'"unclosed',
        source_csv([row()]).replace(b"INV/001", b"INV\x00/001"),
    ],
)
def test_structurally_invalid_sources_are_rejected(source):
    with pytest.raises(ValidationError):
        parse_csv(source)


@pytest.mark.django_db
def test_wrong_column_count_is_a_traceable_row_error(intake):
    content = source_csv([row()]).rstrip(b"\r\n").rsplit(b",", 1)[0] + b"\r\n"
    batch, _ = stage(intake, source_bytes=content)
    preview = preview_import(batch)
    assert preview["rows"][0]["number"] == 2
    assert preview["counts"]["invalid"] == 1
    assert any(p["code"] == "column_count" for p in preview["rows"][0]["issues"])


@pytest.mark.django_db
@pytest.mark.parametrize(
    "value", ["NaN", "Infinity", "-1", "+1", "1.001", "1e3", "1,000.00", "", "99999999999999999.99"]
)
def test_ambiguous_or_out_of_range_money_never_becomes_a_claim(intake, value):
    batch, _ = stage(intake, [row(principal_amount=value)])
    assert preview_import(batch)["counts"]["invalid"] == 1
    with pytest.raises(ValidationError):
        file(intake, batch)
    assert not ReportedClaim.objects.exists()


@pytest.mark.django_db
@pytest.mark.parametrize(
    "changes,expected",
    [
        ({"invoice_total": "1180.01"}, "invalid"),
        ({"reported_due": "1180.01"}, "invalid"),
        ({"reported_due": "0"}, "invalid"),
        ({"currency": "USD"}, "invalid"),
        ({"invoice_date": "2026-02-30"}, "invalid"),
        ({"invoice_delivered_on": "2026-08-01"}, "invalid"),
        ({"broadcast_end": "2026-08-01"}, "invalid"),
        ({"broadcast_start": "2026-07-31", "broadcast_end": "2026-07-01"}, "invalid"),
        ({"financial_year": "2024-2025"}, "invalid"),
        ({"financial_year": "2026-2026"}, "invalid"),
        ({"invoice_number": "\u200bINV001"}, "invalid"),
        ({"invoice_number": "///"}, "invalid"),
        ({"delivery_reference": ""}, "review"),
        ({"invoice_date": "2026-07-15"}, "review"),
        ({"reported_due": "900.00"}, "review"),
        ({"reported_due": "900.00", "balance_explanation": "Unverified source reduction"}, "ready"),
    ],
)
def test_validation_distinguishes_malformed_facts_from_business_review(intake, changes, expected):
    batch, _ = stage(intake, [row(**changes)])
    assert preview_import(batch)["rows"][0]["status"] == expected


@pytest.mark.django_db
def test_decimal_arithmetic_and_large_totals_are_exact(intake):
    maximum = "9999999999999999.99"
    batch, _ = stage(
        intake,
        [
            row(
                invoice_number="MAX/1",
                principal_amount=maximum,
                gst_amount="0",
                invoice_total=maximum,
                reported_due=maximum,
            ),
            row(
                invoice_number="MAX/2",
                principal_amount=maximum,
                gst_amount="0",
                invoice_total=maximum,
                reported_due=maximum,
            ),
            row(
                invoice_number="SMALL/1",
                principal_amount="0.10",
                gst_amount="0.20",
                invoice_total="0.30",
                reported_due="0.30",
            ),
        ],
    )
    preview = preview_import(batch)
    assert preview["ready_reported_total"] == "20000000000000000.28"
    submission, _ = file(intake, batch)
    submission.refresh_from_db()
    assert submission.reported_total == Decimal("20000000000000000.28")


@pytest.mark.django_db
def test_exact_repeated_rows_count_once(intake):
    batch, _ = stage(intake, [row(), row(invoice_number="  inv / 001  ")])
    preview = preview_import(batch)
    assert preview["counts"]["ready"] == preview["counts"]["duplicate"] == 1
    assert preview["rows"][1]["duplicate_of_row"] == 2
    submission, _ = file(intake, batch)
    assert submission.row_count == Invoice.objects.count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize(
    "changes",
    [
        {"principal_amount": "1100", "invoice_total": "1280", "reported_due": "1280"},
        {"invoice_number": "INV-001"},
        {"financial_year": "2025-2026"},
    ],
)
def test_conflicting_rows_cannot_silently_win_by_order(intake, changes):
    batch, _ = stage(intake, [row(), row(**changes)])
    assert preview_import(batch)["counts"]["review"] == 2
    with pytest.raises(ValidationError):
        file(intake, batch)
    assert not Invoice.objects.exists()


@pytest.mark.django_db
def test_corrected_reupload_preserves_already_filed_identities(intake):
    batch, _ = stage(intake, [row(), row(invoice_number="INV/002", invoice_total="1180.01")])
    first, _ = file(intake, batch)
    first_invoice = Invoice.objects.get()
    corrected, _ = stage(
        intake, [row(invoice_number=" ｉｎｖ / ００１ "), row(invoice_number="INV/002")]
    )
    preview = preview_import(corrected)
    assert preview["counts"]["ready"] == preview["counts"]["duplicate"] == 1
    assert preview["rows"][0]["existing_invoice_id"] == str(first_invoice.id)
    second, _ = file(intake, corrected)
    assert first.row_count == second.row_count == 1
    assert Invoice.objects.count() == ReportedClaim.objects.count() == 2


@pytest.mark.django_db
def test_changed_report_is_a_review_not_a_balance_overwrite(intake):
    batch, _ = stage(intake)
    file(intake, batch)
    changed, _ = stage(
        intake, [row(reported_due="900", balance_explanation="Claimed prior reduction")]
    )
    assert preview_import(changed)["counts"]["review"] == 1
    assert ReportedClaim.objects.get().reported_due == Decimal("1180.00")


@pytest.mark.django_db
def test_same_number_in_another_channel_is_independent(intake):
    batch, _ = stage(intake)
    file(intake, batch)
    other, _ = stage(intake, actor=intake.other_checker, organization_id=intake.other_channel.id)
    assert preview_import(other)["counts"]["ready"] == 1
    file(intake, other, actor=intake.other_checker, organization_id=intake.other_channel.id)
    assert Invoice.objects.count() == 2


@pytest.mark.django_db
def test_unshared_or_non_demo_parties_are_not_eligible(intake):
    ClientAccess.objects.filter(client=intake.client, organization=intake.agency).delete()
    batch, _ = stage(intake)
    assert preview_import(batch)["counts"]["invalid"] == 1
    ClientAccess.objects.create(client=intake.client, organization=intake.agency)
    Organization.objects.filter(pk=intake.agency.pk).update(is_demo=False)
    assert preview_import(batch)["counts"]["invalid"] == 1


@pytest.mark.django_db
def test_bounded_sources_have_no_partial_stage_on_overflow(intake):
    content = source_csv([row(invoice_number=f"BOUND/{i}") for i in range(500)])
    assert len(content) < MAX_SOURCE_BYTES
    batch, _ = stage(intake, source_bytes=content)
    assert batch.row_count == 500 and batch.rows.count() == 500
    before = ComplaintImport.objects.count()
    with pytest.raises(ValidationError, match="500"):
        stage(intake, [row(invoice_number=f"OVER/{i}") for i in range(501)])
    assert ComplaintImport.objects.count() == before
    assert hashlib.sha256(bytes(batch.source_bytes)).hexdigest() == batch.source_sha256
