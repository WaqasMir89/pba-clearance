from types import SimpleNamespace

import pytest
from django.core.cache import cache
from django.test import Client as HttpClient

from apps.identity.models import Membership, User
from apps.registry.models import Client, ClientAccess, Organization


@pytest.fixture
def workspace(db):
    cache.clear()
    pba = Organization.objects.create(code="sample-pba", legal_name="Sample Operations", kind="pba")
    channel = Organization.objects.create(
        code="sample-channel", legal_name="Sample Channel", kind="channel"
    )
    agency = Organization.objects.create(
        code="sample-agency", legal_name="Sample Agency", kind="agency"
    )
    other = Organization.objects.create(
        code="sample-other", legal_name="Unrelated Agency", kind="agency"
    )
    officer = User.objects.create_user(username="officer")
    member = User.objects.create_user(username="member")
    auditor = User.objects.create_user(username="auditor")
    pba_membership = Membership.objects.create(user=officer, organization=pba, role="pba_registry")
    membership = Membership.objects.create(user=member, organization=agency, role="agency_preparer")
    Membership.objects.create(user=auditor, organization=pba, role="pba_auditor")
    client = Client.objects.create(
        code="sample-client", legal_name="Sample Client", created_by=officer
    )
    foreign_client = Client.objects.create(
        code="foreign-client", legal_name="Unrelated Client", created_by=officer
    )
    ClientAccess.objects.create(client=client, organization=agency)
    ClientAccess.objects.create(client=foreign_client, organization=other)
    http = HttpClient()
    http.force_login(member)
    return SimpleNamespace(
        pba=pba,
        channel=channel,
        agency=agency,
        other=other,
        officer=officer,
        member=member,
        auditor=auditor,
        membership=membership,
        pba_membership=pba_membership,
        client=client,
        foreign_client=foreign_client,
        http=http,
    )


@pytest.fixture
def intake(workspace):
    from tests.complaints_helpers import prepare_intake

    return prepare_intake(workspace)
