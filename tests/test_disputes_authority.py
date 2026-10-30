from datetime import timedelta
from unittest.mock import patch

import pytest
from django.test import Client as HttpClient
from django.test import override_settings
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from apps.audit.models import AuditEvent, OutboxEvent
from apps.disputes import services
from apps.disputes.models import ClaimEvidence, DisputeCase, DisputeRevision
from apps.identity.models import Membership, User
from apps.registry.models import Client, ClientAccess, Organization
from tests.disputes_helpers import draft, evidence_args, scoped, sign, sign_args, withdraw_args

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("persona", ["maker", "checker", "officer", "auditor", "policy_actor"])
def test_only_agency_roles_can_prepare_an_objection(disputes, persona):
    actor = getattr(disputes, persona)
    organization = disputes.channel if persona in {"maker", "checker"} else disputes.pba
    with pytest.raises(PermissionDenied):
        draft(disputes, actor=actor, organization_id=organization.pk)


def test_agency_preparer_cannot_sign_or_withdraw(disputes):
    candidate, _ = draft(disputes)
    with pytest.raises(PermissionDenied):
        sign(disputes, candidate, actor=disputes.member)
    posted, _ = sign(disputes, candidate)
    with pytest.raises(PermissionDenied):
        services.withdraw(**withdraw_args(disputes, posted, actor=disputes.member))


@pytest.mark.parametrize(
    "state",
    [
        "production",
        "real_user",
        "real_org",
        "real_client",
        "revoked",
        "expired",
        "future",
        "inactive",
    ],
)
def test_current_sandbox_authority_is_rechecked(disputes, state):
    candidate, _ = draft(disputes)
    signer = disputes.agency_signer
    membership = Membership.objects.get(user=signer, organization=disputes.agency)
    if state == "production":
        with override_settings(ENVIRONMENT="production"), pytest.raises(PermissionDenied):
            sign(disputes, candidate)
        return
    if state == "real_user":
        User.objects.filter(pk=signer.pk).update(is_demo=False)
    elif state == "real_org":
        Organization.objects.filter(pk=disputes.agency.pk).update(is_demo=False)
    elif state == "real_client":
        Client.objects.filter(pk=disputes.client.pk).update(is_demo=False)
    elif state == "revoked":
        Membership.objects.filter(pk=membership.pk).update(revoked_at=timezone.now())
    elif state == "expired":
        Membership.objects.filter(pk=membership.pk).update(
            starts_at=timezone.now() - timedelta(days=2), ends_at=timezone.now() - timedelta(days=1)
        )
    elif state == "future":
        Membership.objects.filter(pk=membership.pk).update(
            starts_at=timezone.now() + timedelta(days=1)
        )
    else:
        User.objects.filter(pk=signer.pk).update(is_active=False)
    with pytest.raises(PermissionDenied):
        sign(disputes, candidate)
    assert DisputeRevision.objects.count() == 0


def test_private_drafts_are_never_visible_to_channel_or_oversight(disputes):
    candidate, _ = draft(disputes)
    for actor, organization, status in [
        (disputes.maker, disputes.channel, 403),
        (disputes.auditor, disputes.pba, 403),
        (disputes.foreign_signer, disputes.other, 404),
    ]:
        response = scoped(
            disputes,
            f"/api/v1/objection-drafts/{candidate.pk}/",
            actor=actor,
            organization=organization,
        )
        assert response.status_code == status
        assert candidate.supporting_statement.encode() not in response.content
    assert AuditEvent.objects.filter(action="access.denied").count() == 3


def test_submitted_cases_receipts_and_evidence_follow_claim_parties(disputes):
    candidate, _ = draft(disputes)
    posted, _ = sign(disputes, candidate)
    memo, _ = services.add_evidence(**evidence_args(disputes))
    for actor, organization, expected in [
        (disputes.member, disputes.agency, 200),
        (disputes.maker, disputes.channel, 200),
        (disputes.auditor, disputes.pba, 200),
        (disputes.foreign_signer, disputes.other, 404),
        (disputes.other_checker, disputes.other_channel, 404),
    ]:
        for path in (
            f"/disputes/{posted.case_id}/",
            f"/dispute-revisions/{posted.pk}/receipt/",
            f"/claim-evidence/{memo.pk}/",
        ):
            assert (
                scoped(
                    disputes, "/api/v1" + path, actor=actor, organization=organization
                ).status_code
                == expected
            )
    assert (
        scoped(
            disputes, "/api/v1/disputes/", actor=disputes.policy_actor, organization=disputes.pba
        ).status_code
        == 403
    )


def test_both_parties_may_add_evidence_but_pba_cannot_impersonate_them(disputes):
    own, _ = services.add_evidence(**evidence_args(disputes))
    counter, _ = services.add_evidence(
        **evidence_args(
            disputes,
            actor=disputes.maker,
            organization_id=disputes.channel.pk,
            statement="Fictional channel counterstatement.",
        )
    )
    assert own.organization_id != counter.organization_id
    for actor in (disputes.officer, disputes.auditor, disputes.policy_actor):
        with pytest.raises(PermissionDenied):
            services.add_evidence(
                **evidence_args(disputes, actor=actor, organization_id=disputes.pba.pk)
            )
    assert ClaimEvidence.objects.count() == 2
    assert (
        scoped(disputes, f"/api/v1/claim-evidence/?claim_id={disputes.claim.pk}").json()["count"]
        == 2
    )


def test_registry_visibility_changes_do_not_destroy_historical_party_access(disputes):
    candidate, _ = draft(disputes)
    posted, _ = sign(disputes, candidate)
    ClientAccess.objects.filter(client=disputes.client).delete()
    assert scoped(disputes, f"/api/v1/disputes/{posted.case_id}/").status_code == 200
    assert services.add_evidence(**evidence_args(disputes))[0].claim_id == disputes.claim.pk


@pytest.mark.parametrize("operation", ["submit", "withdraw", "evidence"])
def test_business_history_and_outbox_roll_back_together(disputes, operation):
    candidate, _ = draft(disputes)
    if operation == "withdraw":
        posted, _ = sign(disputes, candidate)

    def invoke():
        if operation == "submit":
            return services.submit_draft(**sign_args(disputes, candidate))
        if operation == "withdraw":
            return services.withdraw(**withdraw_args(disputes, posted))
        return services.add_evidence(**evidence_args(disputes))

    before = (
        DisputeCase.objects.count(),
        DisputeRevision.objects.count(),
        ClaimEvidence.objects.count(),
        AuditEvent.objects.count(),
        OutboxEvent.objects.count(),
    )
    with (
        patch(
            "apps.audit.services.OutboxEvent.objects.create",
            side_effect=RuntimeError("simulated outbox failure"),
        ),
        pytest.raises(RuntimeError),
    ):
        invoke()
    after = (
        DisputeCase.objects.count(),
        DisputeRevision.objects.count(),
        ClaimEvidence.objects.count(),
        AuditEvent.objects.count(),
        OutboxEvent.objects.count(),
    )
    assert after == before


def test_expired_authority_cannot_replay_a_previously_successful_signature(disputes):
    candidate, _ = draft(disputes)
    args = sign_args(disputes, candidate)
    services.submit_draft(**args)
    Membership.objects.filter(user=disputes.agency_signer, organization=disputes.agency).update(
        revoked_at=timezone.now()
    )
    with pytest.raises(PermissionDenied):
        services.submit_draft(**args)


def test_session_capabilities_and_csrf_still_apply(disputes):
    for actor, stage_allowed, sign_allowed, evidence_allowed in [
        (disputes.member, True, False, True),
        (disputes.agency_signer, True, True, True),
        (disputes.maker, False, False, True),
        (disputes.auditor, False, False, False),
    ]:
        http = HttpClient()
        http.force_login(actor)
        membership = http.get("/api/v1/auth/session/").json()["memberships"][0]
        assert membership["can_stage_objections"] is stage_allowed
        assert membership["can_sign_objections"] is sign_allowed
        assert membership["can_add_evidence"] is evidence_allowed
    http = HttpClient(enforce_csrf_checks=True)
    http.force_login(disputes.member)
    assert (
        http.post(
            "/api/v1/objection-drafts/",
            {},
            content_type="application/json",
            HTTP_X_ORGANIZATION_ID=str(disputes.agency.pk),
        ).status_code
        == 403
    )
    assert HttpClient().get("/api/v1/disputes/").status_code == 401
