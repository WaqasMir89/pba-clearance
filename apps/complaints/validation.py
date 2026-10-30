"""Bounded CSV validation. Reported values are never proof of settlement or approved liability."""

import csv
import hashlib
import io
import json
import re
import unicodedata
from collections import defaultdict
from datetime import date
from decimal import Decimal

from rest_framework.exceptions import ValidationError

from apps.complaints.constants import HEADERS, MAX_ROWS, MAX_SOURCE_BYTES, REQUIRED_HEADERS
from apps.complaints.models import Invoice
from apps.registry.models import Client, ClientAccess, Organization


def canonical_json(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


def digest(value):
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def money(value):
    return format(value, ".2f")


def issue(field, code, message):
    return {"field": field, "code": code, "message": message}


def parse_csv(source_bytes):
    if not source_bytes or len(source_bytes) > MAX_SOURCE_BYTES:
        raise ValidationError({"csv": "Choose a nonempty CSV file of at most 256 KiB."})
    try:
        text = source_bytes.decode("utf-8-sig", errors="strict")
    except UnicodeDecodeError as exc:
        raise ValidationError({"csv": "The CSV must use UTF-8 encoding."}) from exc
    if "\x00" in text:
        raise ValidationError({"csv": "The CSV contains an unsupported null character."})
    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    try:
        headers = [cell.strip().lower() for cell in next(reader, [])]
        if len(set(headers)) != len(headers):
            raise ValidationError({"csv": "The CSV contains duplicate column headers."})
        missing, unknown = set(REQUIRED_HEADERS) - set(headers), set(headers) - set(HEADERS)
        if missing:
            raise ValidationError({"csv": "Missing columns: " + ", ".join(sorted(missing))})
        if unknown:
            raise ValidationError(
                {"csv": "The CSV contains unsupported columns. Use the supplied template."}
            )
        rows = []
        for cells in reader:
            if not cells or all(not cell.strip() for cell in cells):
                continue
            if len(rows) >= MAX_ROWS:
                raise ValidationError({"csv": "An import may contain at most 500 data rows."})
            problems = []
            if len(cells) != len(headers):
                problems.append(
                    issue(
                        "row", "column_count", "The row's column count does not match the header."
                    )
                )
            values = dict(zip(headers, cells, strict=False))
            rows.append({"number": reader.line_num, "values": values, "parse_issues": problems})
    except csv.Error as exc:
        raise ValidationError(
            {"csv": "The CSV is malformed. Check quotes, separators and field lengths."}
        ) from exc
    if not rows:
        raise ValidationError({"csv": "The CSV must contain at least one data row."})
    return rows


def normalized_invoice(value):
    normalized = "".join(
        c for c in unicodedata.normalize("NFKC", value).casefold() if not c.isspace()
    )
    comparison = "".join(c for c in normalized if c.isalnum())
    return normalized, comparison


def _source_text(values, field, problems, *, limit=255, required=False):
    value = values.get(field, "").strip()
    if required and not value:
        problems.append(issue(field, "required", "This field is required."))
    if len(value) > limit or any(
        unicodedata.category(c) in {"Cf", "Cs", "Cc"} and not c.isspace() for c in value
    ):
        problems.append(
            issue(
                field, "invalid_text", "The field is too long or contains unsupported characters."
            )
        )
    return value


def _source_date(values, field, problems, *, optional=False):
    value = values.get(field, "").strip()
    if optional and not value:
        return None
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        problems.append(issue(field, "invalid_date", "Use a valid date in YYYY-MM-DD format."))
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        problems.append(issue(field, "invalid_date", "Use a valid date in YYYY-MM-DD format."))
        return None


def _source_money(values, field, problems):
    value = values.get(field, "").strip()
    if not re.fullmatch(r"[0-9]{1,16}(?:\.[0-9]{1,2})?", value):
        problems.append(
            issue(
                field,
                "invalid_amount",
                "Use a nonnegative decimal, at most two fractional places; no grouping/exponent.",
            )
        )
        return None
    return Decimal(value)


def _facts(values, *, channel, cycle, clients, agencies, access):
    problems, reviews = [], []
    agency_code = _source_text(values, "agency_code", problems, limit=40, required=True).lower()
    client_code = _source_text(values, "client_code", problems, limit=40, required=True).lower()
    agency, client = agencies.get(agency_code), clients.get(client_code)
    if not agency:
        problems.append(
            issue(
                "agency_code",
                "unknown_agency",
                "Choose an active fictional agency shared with this channel's clients.",
            )
        )
    if not client:
        problems.append(
            issue("client_code", "unknown_client", "Choose an accessible fictional client.")
        )
    if agency and client and (client.id, agency.id) not in access:
        problems.append(
            issue("client_code", "unshared_client", "The client is not shared with this agency.")
        )
    number = _source_text(values, "invoice_number", problems, limit=120, required=True)
    normalized, comparison = normalized_invoice(number)
    if not comparison or len(normalized) > 240:
        problems.append(
            issue(
                "invoice_number",
                "invalid_identity",
                "Provide a usable invoice identifier of at most 120 characters.",
            )
        )
    year = _source_text(values, "financial_year", problems, limit=9, required=True)
    year_match = re.fullmatch(r"([0-9]{4})-([0-9]{4})", year)
    if not year_match or int(year_match[2]) != int(year_match[1]) + 1:
        problems.append(
            issue(
                "financial_year",
                "invalid_year",
                "Use consecutive source years, for example 2026-2027.",
            )
        )
    dates = {
        field: _source_date(values, field, problems)
        for field in ("invoice_date", "broadcast_start", "broadcast_end")
    }
    delivered = _source_date(values, "invoice_delivered_on", problems, optional=True)
    start, end, invoice_date = (
        dates["broadcast_start"],
        dates["broadcast_end"],
        dates["invoice_date"],
    )
    if (
        start
        and end
        and (start > end or start < cycle.broadcast_start or end > cycle.broadcast_end)
    ):
        problems.append(
            issue(
                "broadcast_end",
                "invalid_period",
                "The ordered broadcast period must fall inside the selected cycle.",
            )
        )
    if invoice_date and end and invoice_date < end:
        reviews.append(
            issue(
                "invoice_date",
                "unusual_invoice_date",
                "The invoice predates the end of its service period and requires review.",
            )
        )
    if delivered and invoice_date and delivered < invoice_date:
        problems.append(
            issue(
                "invoice_delivered_on",
                "invalid_delivery_date",
                "Invoice delivery cannot precede the invoice date.",
            )
        )
    if (
        invoice_date
        and year_match
        and not int(year_match[1]) <= invoice_date.year <= int(year_match[2])
    ):
        problems.append(
            issue(
                "financial_year",
                "year_date_mismatch",
                "The invoice date does not fall within either of the stated source years.",
            )
        )
    amounts = {
        field: _source_money(values, field, problems)
        for field in ("principal_amount", "gst_amount", "invoice_total", "reported_due")
    }
    principal, gst, total, due = (
        amounts[k] for k in ("principal_amount", "gst_amount", "invoice_total", "reported_due")
    )
    if principal is not None and gst is not None and total is not None and principal + gst != total:
        problems.append(
            issue(
                "invoice_total",
                "total_mismatch",
                "Principal plus GST must equal the original invoice total.",
            )
        )
    if total is not None and total <= 0:
        problems.append(
            issue(
                "invoice_total", "nonpositive_total", "The original invoice total must be positive."
            )
        )
    if due is not None and (due <= 0 or (total is not None and due > total)):
        problems.append(
            issue(
                "reported_due",
                "invalid_reported_due",
                "Reported due must be positive and no greater than the original total.",
            )
        )
    currency = _source_text(values, "currency", problems, limit=3, required=True).upper()
    if currency != "PKR":
        problems.append(issue("currency", "unsupported_currency", "This intake supports PKR only."))
    delivery = _source_text(values, "delivery_reference", problems)
    release = _source_text(values, "release_order_reference", problems)
    source_id = _source_text(values, "source_id", problems, limit=120)
    explanation = _source_text(values, "balance_explanation", problems, limit=500)
    if not delivery:
        reviews.append(
            issue(
                "delivery_reference",
                "missing_delivery",
                "A delivery acknowledgement reference is needed for review.",
            )
        )
    if due is not None and total is not None and due < total and not explanation:
        reviews.append(
            issue(
                "balance_explanation",
                "unexplained_reduction",
                "Explain the reduction from the original total. Settlement remains unverified.",
            )
        )
    if problems:
        return None, problems, reviews
    canonical = {
        "channel_id": str(channel.id),
        "agency_id": str(agency.id),
        "agency_code": agency.code,
        "agency_name": agency.legal_name,
        "client_id": str(client.id),
        "client_code": client.code,
        "client_name": client.legal_name,
        "financial_year": year,
        "invoice_number": number,
        "normalized_number": normalized,
        "comparison_key": comparison,
        **{field: value.isoformat() for field, value in dates.items()},
        **{field: money(value) for field, value in amounts.items()},
        "currency": currency,
        "delivery_reference": delivery,
        "invoice_delivered_on": delivered.isoformat() if delivered else None,
        "release_order_reference": release,
        "source_id": source_id,
        "balance_explanation": explanation,
    }
    identity_fields = (
        "channel_id",
        "agency_id",
        "client_id",
        "financial_year",
        "normalized_number",
        "invoice_date",
        "broadcast_start",
        "broadcast_end",
        "principal_amount",
        "gst_amount",
        "invoice_total",
        "reported_due",
        "currency",
    )
    canonical["fingerprint"] = digest({field: canonical[field] for field in identity_fields})
    return canonical, problems, reviews


def validate_rows(rows, *, channel, cycle):
    client_codes = {row.values.get("client_code", "").strip().lower() for row in rows}
    clients = {
        c.code: c
        for c in Client.objects.filter(
            code__in=client_codes, is_demo=True, access_grants__organization=channel
        ).distinct()
    }
    access_rows = list(
        ClientAccess.objects.filter(client_id__in=[c.id for c in clients.values()]).values_list(
            "client_id", "organization_id"
        )
    )
    agency_ids = {organization_id for _, organization_id in access_rows}
    agencies = {
        a.code: a
        for a in Organization.objects.filter(
            pk__in=agency_ids, kind="agency", is_demo=True, is_active=True
        )
    }
    results = []
    access = set(access_rows)
    for row in rows:
        canonical, problems, reviews = _facts(
            row.values,
            channel=channel,
            cycle=cycle,
            clients=clients,
            agencies=agencies,
            access=access,
        )
        problems = list(row.parse_issues) + problems
        results.append(
            {
                "id": str(row.id),
                "number": row.number,
                "values": row.values,
                "canonical": canonical,
                "status": "invalid" if problems else "review" if reviews else "ready",
                "issues": problems + reviews,
                "duplicate_of_row": None,
                "existing_invoice_id": None,
            }
        )
    groups = defaultdict(list)
    for row in results:
        if row["canonical"] and row["status"] != "invalid":
            facts = row["canonical"]
            groups[(facts["agency_id"], facts["comparison_key"])].append(row)
    existing = defaultdict(list)
    for invoice in Invoice.objects.filter(
        channel=channel, comparison_key__in={key[1] for key in groups}
    ).select_related("submission"):
        existing[(str(invoice.agency_id), invoice.comparison_key)].append(invoice)
    for key, group in groups.items():
        fingerprints = {row["canonical"]["fingerprint"] for row in group}
        if len(fingerprints) > 1:
            for row in group:
                row["status"] = "review"
                row["issues"].append(
                    issue(
                        "invoice_number",
                        "conflicting_rows",
                        "This invoice identity has conflicting rows. Review all of them.",
                    )
                )
            continue
        for index, row in enumerate(group):
            facts = row["canonical"]
            matches = existing[key]
            if matches:
                exact = next(
                    (
                        i
                        for i in matches
                        if i.normalized_number == facts["normalized_number"]
                        and i.financial_year == facts["financial_year"]
                        and i.report_fingerprint == facts["fingerprint"]
                        and i.submission.is_sealed
                    ),
                    None,
                )
                if exact and len(matches) == 1:
                    row["status"] = "duplicate"
                    row["existing_invoice_id"] = str(exact.id)
                    row["issues"].append(
                        issue(
                            "invoice_number",
                            "already_reported",
                            "This same invoice report was already filed by this channel.",
                        )
                    )
                else:
                    row["status"] = "review"
                    row["issues"].append(
                        issue(
                            "invoice_number",
                            "existing_collision",
                            "An existing invoice has changed facts, separators or year. "
                            "Review is required.",
                        )
                    )
            elif index and group[0]["status"] == "ready" and row["status"] == "ready":
                row["status"] = "duplicate"
                row["duplicate_of_row"] = group[0]["number"]
                row["issues"].append(
                    issue(
                        "invoice_number",
                        "repeated_row",
                        "This exact report repeats an earlier row in the file.",
                    )
                )
    return results
