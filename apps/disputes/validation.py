import re
import unicodedata
from datetime import UTC
from decimal import Decimal

from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.complaints.validation import money
from apps.disputes.constants import DECLARATIONS


def text(value, field, *, limit, required=True):
    if not isinstance(value, str):
        raise ValidationError({field: "Provide plain text."})
    value = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    if (
        (required and not value)
        or len(value) > limit
        or any(unicodedata.category(c) in {"Cc", "Cf", "Cs"} and c not in "\n\t" for c in value)
    ):
        raise ValidationError(
            {field: f"Provide readable plain text of at most {limit} characters."}
        )
    return value


def amount(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{1,16}(?:\.[0-9]{1,2})?", value):
        raise ValidationError(
            {"disputed_amount": "Use a decimal string with at most two fractional places."}
        )
    parsed = Decimal(value)
    if parsed <= 0:
        raise ValidationError({"disputed_amount": "The disputed amount must be positive."})
    return money(parsed)


def instant(value, field="simulation_at"):
    if not hasattr(value, "tzinfo") or timezone.is_naive(value):
        raise ValidationError({field: "Provide an ISO timestamp with an explicit timezone offset."})
    return value.astimezone(UTC)


def declaration(command_type, version, accepted):
    if accepted is not True or version != DECLARATIONS[command_type]["version"]:
        raise ValidationError(
            {"declaration": "Accept the current sandbox declaration for this command."}
        )


def window_snapshot(window):
    if window is None:
        return None
    return {
        "id": str(window.pk),
        "cycle_id": str(window.cycle_id),
        "opens_at": window.opens_at.isoformat(),
        "closes_at": window.closes_at.isoformat(),
        "timezone": "Asia/Karachi",
        "source_reference": window.source_reference,
        "source_sha256": window.source_sha256,
        "status": "candidate",
        "is_demo": True,
    }


def evidence_timing(window, simulation_at):
    if window is None:
        return "window_unknown"
    if simulation_at < window.opens_at:
        return "before_window"
    if simulation_at >= window.closes_at:
        return "late"
    return "within_window"
