from datetime import UTC, date, datetime, time

import pytest
from django.core.exceptions import ValidationError
from django.db import DatabaseError, transaction
from rest_framework.exceptions import PermissionDenied
from rest_framework.exceptions import ValidationError as ApiValidationError

from apps.audit.models import AuditEvent
from apps.identity.models import Membership, User
from apps.policy.models import ClearanceCycle, Milestone, PolicyVersion
from apps.policy.services import create_candidate_cycle, create_candidate_policy

pytestmark = pytest.mark.django_db


@pytest.fixture
def candidate(workspace):
    actor = User.objects.create_user(username="policy-preparer")
    Membership.objects.create(user=actor, organization=workspace.pba, role="pba_policy_preparer")
    policy = create_candidate_policy(
        actor=actor,
        organization_id=workspace.pba.id,
        code="sample-policy",
        version=1,
        title="Sample Candidate",
        source_reference="fictional reference",
        source_sha256="a" * 64,
        effective_from=date(2026, 1, 1),
        effective_until=date(2027, 1, 1),
    )
    workspace.policy_actor = actor
    workspace.policy = policy
    return workspace


def cycle_input(candidate):
    return {
        "actor": candidate.policy_actor,
        "organization_id": candidate.pba.pk,
        "policy_id": candidate.policy.pk,
        "code": "sample-cycle",
        "title": "Fictional Cycle",
        "broadcast_start": date(2026, 7, 1),
        "broadcast_end": date(2026, 7, 31),
        "milestones": [
            {"code": code, "local_date": date(2026, 10, day), "local_time": time(17, 30)}
            for code, day in [("complaint_open", 5), ("complaint_close", 9), ("payment_cutoff", 19)]
        ],
    }


def test_explicit_local_cutoff_converts_to_utc(candidate):
    cycle = create_candidate_cycle(**cycle_input(candidate))
    milestone = cycle.milestones.get(code="complaint_close")
    assert milestone.local_time == time(17, 30)
    assert milestone.occurs_at == datetime(2026, 10, 9, 12, 30, tzinfo=UTC)
    assert cycle.is_sealed
    assert cycle.policy.status == "candidate"
    assert AuditEvent.objects.filter(action="calendar.candidate_created").exists()


@pytest.mark.parametrize("problem", ["missing", "duplicate", "order", "outside"])
def test_invalid_calendar_is_rejected_without_partial_records(candidate, problem):
    values = cycle_input(candidate)
    if problem == "missing":
        values["milestones"].pop()
    elif problem == "duplicate":
        values["milestones"].append(values["milestones"][0])
    elif problem == "order":
        values["milestones"][1]["local_date"] = date(2026, 10, 1)
    else:
        values["milestones"][0]["local_date"] = date(2025, 10, 1)
    with pytest.raises(ApiValidationError):
        create_candidate_cycle(**values)
    assert not ClearanceCycle.objects.exists()
    assert not Milestone.objects.exists()
    assert not AuditEvent.objects.filter(action="calendar.candidate_created").exists()


def test_date_only_milestone_api_cannot_invent_a_cutoff(candidate):
    candidate.http.force_login(candidate.policy_actor)
    response = candidate.http.post(
        "/api/v1/cycles/",
        {
            "code": "missing-time",
            "title": "Candidate",
            "policy_id": str(candidate.policy.id),
            "broadcast_start": "2026-07-01",
            "broadcast_end": "2026-07-31",
            "milestones": [
                {"code": code, "local_date": "2026-10-05"}
                for code in ["complaint_open", "complaint_close", "payment_cutoff"]
            ],
        },
        content_type="application/json",
        HTTP_X_ORGANIZATION_ID=str(candidate.pba.id),
    )
    assert response.status_code == 400
    assert not ClearanceCycle.objects.exists()


def test_registry_officer_cannot_prepare_policy(candidate):
    with pytest.raises(PermissionDenied):
        create_candidate_policy(
            actor=candidate.officer,
            organization_id=candidate.pba.id,
            code="blocked",
            version=1,
            title="Blocked",
            source_reference="fictional",
            source_sha256="a" * 64,
            effective_from=date(2026, 1, 1),
        )


def test_source_digest_is_validated(candidate):
    with pytest.raises(ValidationError):
        create_candidate_policy(
            actor=candidate.policy_actor,
            organization_id=candidate.pba.id,
            code="invalid",
            version=1,
            title="Invalid",
            source_reference="fictional",
            source_sha256="not-a-digest",
            effective_from=date(2026, 1, 1),
        )


def test_invalid_policy_interval_has_an_actionable_field_error(candidate):
    with pytest.raises(ValidationError) as error:
        create_candidate_policy(
            actor=candidate.policy_actor,
            organization_id=candidate.pba.id,
            code="bad-interval",
            version=1,
            title="Invalid Candidate",
            source_reference="fictional",
            source_sha256="a" * 64,
            effective_from=date(2026, 11, 1),
            effective_until=date(2026, 10, 1),
        )
    assert error.value.message_dict["effective_until"] == [
        "The end date must be after the start date."
    ]
    assert not PolicyVersion.objects.filter(code="bad-interval").exists()


@pytest.mark.parametrize("target", ["policy", "cycle", "milestone"])
def test_snapshot_updates_are_database_rejected(candidate, target):
    cycle = create_candidate_cycle(**cycle_input(candidate))
    with pytest.raises(DatabaseError), transaction.atomic():
        if target == "policy":
            PolicyVersion.objects.filter(pk=candidate.policy.pk).update(title="Changed")
        elif target == "cycle":
            ClearanceCycle.objects.filter(pk=cycle.pk).update(title="Changed")
        else:
            Milestone.objects.filter(cycle=cycle).update(local_time=time(23, 59))


def test_sealed_calendar_cannot_gain_new_milestones(candidate):
    cycle = create_candidate_cycle(**cycle_input(candidate))
    with pytest.raises(DatabaseError), transaction.atomic():
        Milestone.objects.create(
            cycle=cycle,
            code="committee",
            local_date=date(2026, 10, 22),
            local_time=time(11),
            occurs_at=datetime(2026, 10, 22, 6, tzinfo=UTC),
        )
    assert cycle.milestones.count() == 3


def test_utc_and_local_time_cannot_disagree_at_database_boundary(candidate):
    cycle = ClearanceCycle.objects.create(
        created_by=candidate.policy_actor,
        policy=candidate.policy,
        code="unsealed",
        title="Unsealed",
        broadcast_start=date(2026, 7, 1),
        broadcast_end=date(2026, 7, 31),
    )
    with pytest.raises(DatabaseError), transaction.atomic():
        Milestone.objects.create(
            cycle=cycle,
            code="committee",
            local_date=date(2026, 10, 22),
            local_time=time(11),
            occurs_at=datetime(2026, 10, 22, 11, tzinfo=UTC),
        )


def test_candidate_policy_cannot_be_promoted_with_an_update(candidate):
    with pytest.raises(DatabaseError), transaction.atomic():
        PolicyVersion.objects.filter(pk=candidate.policy.id).update(status="approved")
    candidate.policy.refresh_from_db()
    assert candidate.policy.status == "candidate"


def test_real_member_cannot_read_candidate_policy_or_calendar(candidate):
    create_candidate_cycle(**cycle_input(candidate))
    assert (
        candidate.http.get(
            "/api/v1/policies/", HTTP_X_ORGANIZATION_ID=str(candidate.agency.id)
        ).status_code
        == 403
    )
    assert (
        candidate.http.get(
            "/api/v1/cycles/", HTTP_X_ORGANIZATION_ID=str(candidate.agency.id)
        ).json()["count"]
        == 0
    )


def test_new_policy_version_preserves_original_cycle(candidate):
    cycle = create_candidate_cycle(**cycle_input(candidate))
    new = create_candidate_policy(
        actor=candidate.policy_actor,
        organization_id=candidate.pba.id,
        code="sample-policy",
        version=2,
        title="New Candidate",
        source_reference="fictional reference v2",
        source_sha256="b" * 64,
        effective_from=date(2027, 1, 1),
    )
    cycle.refresh_from_db()
    assert cycle.policy_id == candidate.policy.id != new.id
    assert cycle.policy.source_sha256 == "a" * 64
