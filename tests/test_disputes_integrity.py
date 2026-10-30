import time
from datetime import timedelta
from uuid import uuid4

import pytest
from django.db import DatabaseError, connection, transaction
from django.utils import timezone

from apps.disputes import services
from apps.disputes.models import ClaimEvidence, DisputeCase, DisputeRevision, ObjectionDraft
from apps.identity.models import Membership
from tests.disputes_helpers import draft, evidence_args, sign

pytestmark = pytest.mark.django_db


def records(ctx):
    candidate, _ = draft(ctx)
    revision, _ = sign(ctx, candidate)
    memo, _ = services.add_evidence(**evidence_args(ctx))
    return {
        "window": ctx.response_window,
        "draft": candidate,
        "case": revision.case,
        "revision": revision,
        "evidence": memo,
    }


def copied(record, **changes):
    fields = {
        field.attname: getattr(record, field.attname)
        for field in record._meta.concrete_fields
        if not field.primary_key
    }
    if "idempotency_key" in fields:
        fields["idempotency_key"] = uuid4()
    return {**fields, **changes}


@pytest.mark.parametrize("kind", ["window", "draft", "case", "revision", "evidence"])
@pytest.mark.parametrize("operation", ["update", "delete"])
def test_raw_sql_cannot_rewrite_or_remove_dispute_history(disputes, kind, operation):
    record = records(disputes)[kind]
    table = connection.ops.quote_name(record._meta.db_table)
    with pytest.raises(DatabaseError, match="immutable"), transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute(
                f"UPDATE {table} SET id=id WHERE id=%s"
                if operation == "update"
                else f"DELETE FROM {table} WHERE id=%s",
                [record.pk],
            )
    assert type(record).objects.filter(pk=record.pk).exists()


def test_database_rejects_draft_amount_above_original_report(disputes):
    candidate, _ = draft(disputes)
    with pytest.raises(DatabaseError, match="scope, amount or authority"), transaction.atomic():
        ObjectionDraft.objects.create(**copied(candidate, disputed_amount="1180.01"))


def test_database_rejects_forged_case_parties(disputes):
    candidate, _ = draft(disputes)
    revision, _ = sign(disputes, candidate)
    with pytest.raises(DatabaseError, match="filed claim"), transaction.atomic():
        DisputeCase.objects.create(**copied(revision.case, agency_id=disputes.other.pk))


@pytest.mark.parametrize("version", [1, 3])
def test_database_requires_the_next_case_version(disputes, version):
    candidate, _ = draft(disputes)
    revision, _ = sign(disputes, candidate)
    with pytest.raises(DatabaseError, match="next case version"), transaction.atomic():
        DisputeRevision.objects.create(**copied(revision, version=version))
    assert DisputeRevision.objects.count() == 1


def test_database_cannot_reuse_a_previously_signed_draft(disputes):
    candidate, _ = draft(disputes)
    revision, _ = sign(disputes, candidate)
    with pytest.raises(DatabaseError, match="stale"), transaction.atomic():
        DisputeRevision.objects.create(**copied(revision, version=2))


def test_database_cannot_claim_that_an_evidence_memo_verified_payment(disputes):
    memo, _ = services.add_evidence(**evidence_args(disputes))
    with pytest.raises(DatabaseError, match="matching receipt"), transaction.atomic():
        ClaimEvidence.objects.create(
            **copied(memo, receipt={**memo.receipt, "financial_effect": "paid"})
        )


def test_database_checks_live_expiry_after_transaction_start(disputes):
    candidate, _ = draft(disputes)
    revision, _ = sign(disputes, candidate)
    now = timezone.now()
    Membership.objects.filter(user=disputes.agency_signer, organization=disputes.agency).update(
        starts_at=now - timedelta(days=1), ends_at=now + timedelta(milliseconds=150)
    )
    time.sleep(0.2)
    with pytest.raises(DatabaseError, match="current authority"), transaction.atomic():
        DisputeRevision.objects.create(**copied(revision, version=2))


def test_orm_instance_guards_also_preserve_history(disputes):
    for record in records(disputes).values():
        with pytest.raises(TypeError):
            record.save()
        with pytest.raises(TypeError):
            record.delete()
