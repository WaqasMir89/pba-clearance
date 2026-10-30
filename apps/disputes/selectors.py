from decimal import Decimal

from django.db.models import Case, CharField, DecimalField, OuterRef, Subquery, Value, When
from django.db.models.functions import Coalesce
from rest_framework.exceptions import PermissionDenied

from apps.complaints.selectors import AGENCY_ROLES, claims_for
from apps.disputes.models import ClaimEvidence, DisputeCase, DisputeRevision, ObjectionDraft


def drafts_for(membership):
    if membership.role not in AGENCY_ROLES:
        raise PermissionDenied("Unsubmitted objection drafts are private to their agency.")
    return ObjectionDraft.objects.filter(agency_id=membership.organization_id)


def cases_for(membership):
    return DisputeCase.objects.filter(
        claim__in=claims_for(membership), revisions__isnull=False
    ).distinct()


def revisions_for(membership):
    return DisputeRevision.objects.filter(case__claim__in=claims_for(membership))


def evidence_for(membership):
    return ClaimEvidence.objects.filter(claim__in=claims_for(membership))


def with_objections(queryset, *, case=False):
    latest = DisputeRevision.objects.filter(
        **({"case_id": OuterRef("pk")} if case else {"case__claim_id": OuterRef("pk")})
    ).order_by("-version")
    queryset = queryset.annotate(
        objection_case_id=Subquery(latest.values("case_id")[:1]),
        objection_revision_id=Subquery(latest.values("id")[:1]),
        objection_version=Coalesce(Subquery(latest.values("version")[:1]), 0),
        objection_action=Subquery(latest.values("action")[:1]),
        disputed_amount=Coalesce(
            Subquery(latest.values("disputed_amount")[:1]),
            Value(Decimal("0.00")),
            output_field=DecimalField(max_digits=18, decimal_places=2),
        ),
    )
    return queryset.annotate(
        objection_state=Case(
            When(objection_action__isnull=True, then=Value("none")),
            When(objection_action="withdrawn", then=Value("withdrawn")),
            default=Value("open"),
            output_field=CharField(),
        )
    )
