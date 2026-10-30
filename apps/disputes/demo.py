import hashlib
from datetime import datetime
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo

from django.conf import settings

from apps.disputes.models import SandboxResponseWindow
from apps.disputes.services import create_window
from apps.policy.models import ClearanceCycle


def seed_response_window(*, actor, organization_id):
    cycle = ClearanceCycle.objects.get(code="demo-july-2026-v1")
    if SandboxResponseWindow.objects.filter(cycle=cycle).exists():
        return
    reference = "examples/candidate-response-window.txt"
    create_window(
        actor=actor,
        organization_id=organization_id,
        cycle_id=cycle.pk,
        opens_at=datetime(2026, 10, 12, 10, tzinfo=ZoneInfo("Asia/Karachi")),
        closes_at=datetime(2026, 10, 16, 17, tzinfo=ZoneInfo("Asia/Karachi")),
        source_reference=reference,
        source_sha256=hashlib.sha256((settings.BASE_DIR / reference).read_bytes()).hexdigest(),
        idempotency_key=uuid5(NAMESPACE_URL, f"pba-clearance:sandbox-response-window:{cycle.pk}"),
    )
