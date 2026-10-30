import base64
import hashlib
from decimal import Decimal

import pytest

from apps.complaints.models import ComplaintImport, Invoice, ReportedClaim, Submission
from apps.complaints.services import import_detail, preview_import
from apps.complaints.validation import canonical_json
from tests.complaints_helpers import file, row, stage

pytestmark = pytest.mark.django_db


def test_staging_is_not_a_filed_claim(intake):
    batch, replayed = stage(intake)
    assert not replayed and batch.is_sealed
    preview = preview_import(batch)
    assert preview["counts"] == {"ready": 1, "invalid": 0, "review": 0, "duplicate": 0}
    assert preview["ready_reported_total"] == "1180.00"
    assert not Invoice.objects.exists() and not ReportedClaim.objects.exists()


def test_filing_posts_exact_claim_and_reproducible_receipt(intake):
    batch, _ = stage(intake)
    before = preview_import(batch)
    submission, replayed = file(intake, batch)
    assert not replayed and submission.is_sealed
    assert Invoice.objects.count() == ReportedClaim.objects.count() == 1
    assert submission.reported_total == "1180.00"
    assert ReportedClaim.objects.get().reported_due == Decimal("1180.00")
    assert (
        hashlib.sha256(canonical_json(submission.receipt).encode()).hexdigest()
        == submission.content_hash
    )
    detail = import_detail(batch)
    assert detail["submission_id"] == submission.id and not detail["preview_current"]
    assert detail["preview"]["preview_hash"] == before["preview_hash"]


def test_mixed_file_only_files_ready_rows(intake):
    batch, _ = stage(intake, [row(), row(invoice_number="INV/002", invoice_total="1180.01")])
    preview = preview_import(batch)
    assert preview["counts"]["invalid"] == 1
    submission, _ = file(intake, batch)
    assert submission.row_count == 1
    assert submission.receipt["excluded_rows"] == [{"number": 3, "status": "invalid"}]


def test_api_stage_file_and_private_receipt(intake):
    batch, _ = stage(intake)
    from tests.complaints_helpers import filing_args

    intake.http.force_login(intake.checker)
    data = filing_args(intake, batch)
    for key in ["actor", "organization_id", "import_id"]:
        data.pop(key)
    data["simulation_at"] = data["simulation_at"].isoformat()
    data["idempotency_key"] = str(data["idempotency_key"])
    response = intake.http.post(
        f"/api/v1/complaint-imports/{batch.id}/submit/",
        data,
        content_type="application/json",
        HTTP_X_ORGANIZATION_ID=str(intake.channel.id),
    )
    assert response.status_code == 201, response.content
    receipt = intake.http.get(
        f"/api/v1/complaint-submissions/{response.json()['id']}/receipt/",
        HTTP_X_ORGANIZATION_ID=str(intake.channel.id),
    )
    assert hashlib.sha256(receipt.content).hexdigest() == response.json()["content_hash"]
    assert receipt["Cache-Control"] == "no-store, private"


def test_api_upload_decodes_original_bytes(intake):
    from uuid import uuid4

    from tests.complaints_helpers import source_csv

    content = b"\xef\xbb\xbf" + source_csv([row()])
    intake.http.force_login(intake.maker)
    response = intake.http.post(
        "/api/v1/complaint-imports/",
        {
            "cycle_id": str(intake.cycle.id),
            "source_filename": "fictional.csv",
            "csv_base64": base64.b64encode(content).decode(),
            "idempotency_key": str(uuid4()),
        },
        content_type="application/json",
        HTTP_X_ORGANIZATION_ID=str(intake.channel.id),
    )
    assert response.status_code == 201, response.content
    batch = ComplaintImport.objects.get(pk=response.json()["id"])
    assert bytes(batch.source_bytes) == content
    assert batch.source_sha256 == hashlib.sha256(content).hexdigest()
    assert response.json()["preview"]["counts"]["ready"] == 1
    assert Submission.objects.count() == 0
