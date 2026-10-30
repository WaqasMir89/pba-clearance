from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from django.db import close_old_connections, connection, connections

from apps.audit.models import AuditEvent
from apps.complaints.errors import PreviewChanged
from apps.complaints.models import ComplaintImport, Invoice, ReportedClaim, Submission
from apps.complaints.services import file_import, stage_import
from apps.identity.models import User
from tests.complaints_helpers import filing_args, row, source_csv, stage

pytestmark = pytest.mark.django_db(transaction=True)


def concurrent_calls(callback):
    barrier = Barrier(2)

    def worker(index):
        close_old_connections()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET statement_timeout = '6s'")
                cursor.execute(
                    "SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user"
                )
                assert cursor.fetchone() == (False, False)
            barrier.wait(timeout=6)
            return callback(index)
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(worker, index) for index in range(2)]
        return [future.result(timeout=15) for future in futures]


def test_simultaneous_stage_requests_share_one_immutable_import(intake):
    key, content = uuid4(), source_csv([row()])

    def call(index):
        batch, replayed = stage_import(
            actor=User.objects.get(pk=intake.maker.pk),
            organization_id=intake.channel.pk,
            cycle_id=intake.cycle.pk,
            source_filename="fictional.csv",
            source_bytes=content,
            idempotency_key=key,
        )
        return str(batch.pk), replayed

    results = concurrent_calls(call)
    assert results[0][0] == results[1][0]
    assert sorted(result[1] for result in results) == [False, True]
    assert ComplaintImport.objects.count() == 1
    assert AuditEvent.objects.filter(action="complaints.import_staged").count() == 1


def test_simultaneous_same_key_filings_return_one_receipt(intake):
    batch, _ = stage(intake)
    arguments = filing_args(intake, batch)

    def call(index):
        submission, replayed = file_import(
            **{**arguments, "actor": User.objects.get(pk=intake.checker.pk)}
        )
        return str(submission.pk), replayed

    results = concurrent_calls(call)
    assert results[0][0] == results[1][0]
    assert sorted(result[1] for result in results) == [False, True]
    assert (
        Submission.objects.count() == Invoice.objects.count() == ReportedClaim.objects.count() == 1
    )
    assert AuditEvent.objects.filter(action="complaints.submitted").count() == 1


def test_simultaneous_different_imports_cannot_double_report_an_invoice(intake):
    first, _ = stage(intake)
    second, _ = stage(intake)
    arguments = [filing_args(intake, first), filing_args(intake, second)]

    def call(index):
        try:
            submission, _ = file_import(
                **{**arguments[index], "actor": User.objects.get(pk=intake.checker.pk)}
            )
            return "created", str(submission.pk)
        except PreviewChanged:
            return "stale", None

    results = concurrent_calls(call)
    assert sorted(result[0] for result in results) == ["created", "stale"]
    assert (
        Submission.objects.count() == Invoice.objects.count() == ReportedClaim.objects.count() == 1
    )
