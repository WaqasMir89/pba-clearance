from datetime import UTC, datetime
from itertools import pairwise
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import IntegrityError, transaction
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.audit.services import record_event
from apps.identity.models import Membership
from apps.identity.selectors import workspace_membership
from apps.policy.models import ClearanceCycle, Milestone, PolicyVersion

POLICY_READ_ROLES = {
    Membership.Role.PBA_REGISTRY,
    Membership.Role.PBA_AUDITOR,
    Membership.Role.PBA_POLICY_PREPARER,
}


def require_policy_preparer(actor, organization_id):
    membership = workspace_membership(actor, organization_id, lock=True)
    if (
        settings.ENVIRONMENT != "development"
        or membership.role != Membership.Role.PBA_POLICY_PREPARER
    ):
        raise PermissionDenied("Candidate configuration requires an authorized policy preparer.")
    return membership


@transaction.atomic
def create_candidate_policy(*, actor, organization_id, request_id=None, **fields):
    membership = require_policy_preparer(actor, organization_id)
    fields["code"] = fields["code"].strip().lower()
    fields["is_demo"] = membership.organization.is_demo
    policy = PolicyVersion(created_by=actor, **fields)
    policy.full_clean()
    try:
        with transaction.atomic():
            policy.save(force_insert=True)
    except IntegrityError as exc:
        raise ValidationError({"version": "This policy version already exists."}) from exc
    record_event(
        actor=actor,
        organization_id=organization_id,
        action="policy.candidate_created",
        subject=policy,
        details={"code": policy.code, "version": policy.version, "status": "candidate"},
        request_id=request_id,
    )
    return policy


@transaction.atomic
def create_candidate_cycle(
    *, actor, organization_id, policy_id, milestones, request_id=None, **fields
):
    require_policy_preparer(actor, organization_id)
    fields["code"] = fields["code"].strip().lower()
    policy = PolicyVersion.objects.filter(pk=policy_id).first()
    if policy is None:
        raise ValidationError({"policy_id": "Choose an existing candidate policy."})
    cycle = ClearanceCycle(created_by=actor, policy=policy, **fields)
    cycle.full_clean()
    codes = [m["code"] for m in milestones]
    if len(codes) != len(set(codes)):
        raise ValidationError({"milestones": "Each milestone must occur once per cycle."})
    required = {"complaint_open", "complaint_close", "payment_cutoff"}
    if not required.issubset(codes):
        raise ValidationError(
            {"milestones": "Provide filing open, filing close and payment cutoff."}
        )
    records = []
    for milestone in milestones:
        if milestone["local_time"].tzinfo is not None:
            raise ValidationError({"milestones": "Provide local time without an offset."})
        instant = datetime.combine(
            milestone["local_date"], milestone["local_time"], tzinfo=ZoneInfo("Asia/Karachi")
        ).astimezone(UTC)
        if milestone["local_date"] < policy.effective_from or (
            policy.effective_until and milestone["local_date"] >= policy.effective_until
        ):
            raise ValidationError(
                {"milestones": "Milestones must fall inside the policy interval."}
            )
        record = Milestone(cycle=cycle, occurs_at=instant, **milestone)
        record.full_clean(exclude=["cycle"])
        records.append(record)
    order = list(Milestone.Code.values)
    ordered = sorted(records, key=lambda m: order.index(m.code))
    if any(left.occurs_at >= right.occurs_at for left, right in pairwise(ordered)):
        raise ValidationError(
            {"milestones": "Milestones must follow the displayed workflow order."}
        )
    try:
        with transaction.atomic():
            cycle.save(force_insert=True)
    except IntegrityError as exc:
        raise ValidationError({"code": "This cycle identifier already exists."}) from exc
    Milestone.objects.bulk_create(records)
    ClearanceCycle.objects.filter(pk=cycle.pk).update(is_sealed=True)
    cycle.is_sealed = True
    record_event(
        actor=actor,
        organization_id=organization_id,
        action="calendar.candidate_created",
        subject=cycle,
        details={"policy_id": str(policy.id), "milestones": len(records)},
        request_id=request_id,
    )
    return cycle
