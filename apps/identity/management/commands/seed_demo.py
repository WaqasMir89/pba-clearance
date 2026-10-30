import getpass
import os
import sys

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.audit.services import record_event
from apps.identity.models import Membership, User
from apps.registry.models import Organization
from apps.registry.services import create_client


class Command(BaseCommand):
    help = "Provision explicitly fictional local workspaces. Never resets existing passwords."

    @transaction.atomic
    def handle(self, *args, **options):
        if settings.ENVIRONMENT != "development":
            raise CommandError("Demo provisioning is available only in development.")
        password = os.environ.get("CLEARANCE_DEMO_PASSWORD")
        if not password and sys.stdin.isatty():
            password = getpass.getpass("Choose a local demo password (12+ characters): ")
        if not password:
            raise CommandError("Set CLEARANCE_DEMO_PASSWORD or run from an interactive terminal.")
        try:
            validate_password(password)
        except ValidationError as exc:
            raise CommandError(" ".join(exc.messages)) from exc

        users = {}
        for label in ["pba", "channel", "agency", "reviewer", "policy", "approver"]:
            user, created = User.objects.get_or_create(
                username=f"demo.{label}",
                defaults={"first_name": "Demo", "last_name": label.title(), "is_demo": True},
            )
            if not user.is_demo:
                raise CommandError("A demo username collides with a non-demo account.")
            if created:
                user.set_password(password)
                user.save(update_fields=["password"])
            users[label] = user

        organizations = {}
        specs = [
            ("pba", "Sample Association Operations", "pba"),
            ("north", "Sample North Television", "channel"),
            ("coast", "Sample Coast Television", "channel"),
            ("studio", "Sample Studio Agency", "agency"),
            ("orbit", "Sample Orbit Agency", "agency"),
        ]
        for key, name, kind in specs:
            organization, created = Organization.objects.get_or_create(
                code=f"demo-{key}",
                defaults={
                    "legal_name": name,
                    "kind": kind,
                    "is_demo": True,
                    "created_by": users["pba"],
                },
            )
            if not organization.is_demo or organization.kind != kind:
                raise CommandError("A demo identifier collides with an unrelated organization.")
            if created:
                record_event(
                    actor=users["pba"],
                    organization_id=organization.pk,
                    action="demo.organization_provisioned",
                    subject=organization,
                    details={"fictional": True},
                )
            organizations[key] = organization

        memberships = [
            ("pba", "pba", Membership.Role.PBA_REGISTRY),
            ("channel", "north", Membership.Role.CHANNEL_PREPARER),
            ("channel", "coast", Membership.Role.CHANNEL_PREPARER),
            ("agency", "studio", Membership.Role.AGENCY_PREPARER),
            ("agency", "orbit", Membership.Role.AGENCY_PREPARER),
            ("reviewer", "pba", Membership.Role.PBA_AUDITOR),
            ("policy", "pba", Membership.Role.PBA_POLICY_PREPARER),
            ("approver", "north", Membership.Role.CHANNEL_APPROVER),
            ("approver", "coast", Membership.Role.CHANNEL_APPROVER),
        ]
        for who, workspace, role in memberships:
            membership, created = Membership.objects.get_or_create(
                user=users[who], organization=organizations[workspace], defaults={"role": role}
            )
            if membership.role != role:
                raise CommandError("An existing demo membership has changed; review it manually.")
            if created:
                membership.full_clean()
                record_event(
                    actor=users["pba"],
                    organization_id=membership.organization_id,
                    action="demo.membership_provisioned",
                    subject=membership,
                    details={"fictional": True},
                )

        from apps.registry.models import Client

        for code, name, participants in [
            ("loom", "Sample Loom Textiles", ["north", "studio"]),
            ("cedar", "Sample Cedar Foods", ["coast", "orbit"]),
            ("metro", "Sample Metro Mobility", ["north", "studio"]),
        ]:
            existing = Client.objects.filter(code=f"demo-{code}").first()
            if existing:
                if not existing.is_demo:
                    raise CommandError("A demo client identifier collides with a non-demo record.")
                continue
            create_client(
                actor=users["pba"],
                organization_id=organizations["pba"].pk,
                legal_name=name,
                code=f"demo-{code}",
                participant_ids=[organizations[key].pk for key in participants],
                is_demo=True,
            )
        from apps.policy.demo import seed_candidate_configuration

        seed_candidate_configuration(actor=users["policy"], organization_id=organizations["pba"].pk)
        self.stdout.write(
            self.style.SUCCESS(
                "Fictional workspaces ready: demo.pba, demo.channel, demo.agency, "
                "demo.reviewer, demo.policy, demo.approver. "
                "Existing passwords, revocations and records were preserved."
            )
        )
