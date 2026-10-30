import hashlib
from datetime import date, time

from django.conf import settings

from apps.policy.models import ClearanceCycle, PolicyVersion
from apps.policy.services import create_candidate_cycle, create_candidate_policy


def seed_candidate_configuration(*, actor, organization_id):
    """Explicitly fictional dates; not derived from the unapproved workflow account."""
    policy = PolicyVersion.objects.filter(code="demo-clearance", version=1).first()
    if policy is None:
        source = (settings.BASE_DIR / "examples/candidate-policy.txt").read_bytes()
        policy = create_candidate_policy(
            actor=actor,
            organization_id=organization_id,
            code="demo-clearance",
            version=1,
            title="Fictional clearance configuration",
            source_reference="examples/candidate-policy.txt",
            source_sha256=hashlib.sha256(source).hexdigest(),
            effective_from=date(2026, 1, 1),
            effective_until=date(2027, 1, 1),
            is_demo=True,
        )
    elif not policy.is_demo:
        raise ValueError("Demo policy identifier collides with a non-demo record.")
    if ClearanceCycle.objects.filter(code="demo-july-2026-v1").exists():
        return
    create_candidate_cycle(
        actor=actor,
        organization_id=organization_id,
        code="demo-july-2026-v1",
        title="July 2026 broadcast · fictional calendar",
        policy_id=policy.pk,
        broadcast_start=date(2026, 7, 1),
        broadcast_end=date(2026, 7, 31),
        milestones=[
            {"code": code, "local_date": date(2026, 10, day), "local_time": time(hour, 0)}
            for code, day, hour in [
                ("complaint_open", 5, 9),
                ("complaint_close", 9, 17),
                ("circulation", 12, 10),
                ("payment_cutoff", 19, 17),
                ("committee", 22, 11),
            ]
        ],
    )
