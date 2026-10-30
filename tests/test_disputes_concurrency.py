import pytest

from apps.audit.models import AuditEvent
from apps.disputes import services
from apps.disputes.errors import PreviewConflict, VersionConflict
from apps.disputes.models import ClaimEvidence, DisputeCase, DisputeRevision, ObjectionDraft
from apps.identity.models import User
from tests.disputes_helpers import draft, draft_args, evidence_args, sign, sign_args, withdraw_args
from tests.test_complaints_concurrency import concurrent_calls

pytestmark = pytest.mark.django_db(transaction=True)


def test_simultaneous_same_key_drafts_have_one_record(disputes):
    args = draft_args(disputes)

    def call(index):
        result, replayed = services.stage_draft(
            **{**args, "actor": User.objects.get(pk=disputes.member.pk)}
        )
        return result.pk, replayed

    results = concurrent_calls(call)
    assert results[0][0] == results[1][0]
    assert sorted(result[1] for result in results) == [False, True]
    assert ObjectionDraft.objects.count() == 1


def test_simultaneous_same_key_signatures_have_one_revision(disputes):
    candidate, _ = draft(disputes)
    args = sign_args(disputes, candidate)

    def call(index):
        result, replayed = services.submit_draft(
            **{**args, "actor": User.objects.get(pk=disputes.agency_signer.pk)}
        )
        return result.pk, replayed

    results = concurrent_calls(call)
    assert results[0][0] == results[1][0]
    assert sorted(result[1] for result in results) == [False, True]
    assert DisputeRevision.objects.count() == DisputeCase.objects.count() == 1
    assert AuditEvent.objects.filter(action="disputes.raised").count() == 1


def test_competing_drafts_cannot_both_become_the_first_revision(disputes):
    first, _ = draft(disputes)
    second, _ = draft(disputes, disputed_amount="50.00")
    args = [sign_args(disputes, first), sign_args(disputes, second)]

    def call(index):
        try:
            result, _ = services.submit_draft(
                **{**args[index], "actor": User.objects.get(pk=disputes.agency_signer.pk)}
            )
            return "created", result.pk
        except (PreviewConflict, VersionConflict):
            return "stale", None

    results = concurrent_calls(call)
    assert sorted(result[0] for result in results) == ["created", "stale"]
    assert DisputeCase.objects.count() == DisputeRevision.objects.count() == 1


def test_withdrawal_and_amendment_race_preserves_one_next_version(disputes):
    first, _ = draft(disputes)
    current, _ = sign(disputes, first)
    amendment, _ = draft(disputes, expected_case_version=1, disputed_amount="50.00")
    submit = sign_args(disputes, amendment)
    withdrawal = withdraw_args(disputes, current)

    def call(index):
        try:
            actor = User.objects.get(pk=disputes.agency_signer.pk)
            result, _ = (
                services.submit_draft(**{**submit, "actor": actor})
                if index == 0
                else services.withdraw(**{**withdrawal, "actor": actor})
            )
            return "created", result.version
        except (PreviewConflict, VersionConflict):
            return "stale", None

    results = concurrent_calls(call)
    assert sorted(result[0] for result in results) == ["created", "stale"]
    assert list(DisputeRevision.objects.order_by("version").values_list("version", flat=True)) == [
        1,
        2,
    ]


def test_simultaneous_evidence_replays_do_not_duplicate_a_statement(disputes):
    args = evidence_args(disputes)

    def call(index):
        result, replayed = services.add_evidence(
            **{**args, "actor": User.objects.get(pk=disputes.member.pk)}
        )
        return result.pk, replayed

    results = concurrent_calls(call)
    assert results[0][0] == results[1][0]
    assert sorted(result[1] for result in results) == [False, True]
    assert ClaimEvidence.objects.count() == 1
