"""Compliance & sign-off register: access control, sign-off flow, overdue alerts."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Organization, ProjectTask, UserAccount, UserCategory
from accounts.roles import SENIOR_SITE_MANAGER
from buildwatch.compliance import generate_checkpoints_for_tender
from buildwatch.models import (
    BidderRegistration,
    ComplianceCheckpoint,
    Country,
    EvaluationEvent,
    InfraProject,
    TenderListing,
    TenderPreamble,
)


class ComplianceSignoffTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.cat = UserCategory.objects.create(code=SENIOR_SITE_MANAGER, description="SSM", rank=30)
        cls.ke, _ = Country.objects.get_or_create(
            code="KE",
            defaults={"name": "Kenya", "currency_code": "KES", "currency_symbol": "KES"},
        )
        cls.sponsor = Organization.objects.create(
            org_code="SDHUD", name="State Dept Housing", short_name="Housing",
            organization_type="GOV_NATIONAL", registration_status=Organization.STATUS_ACTIVE,
            email="sponsor@example.com",
        )
        cls.contractor = Organization.objects.create(
            org_code="PIONEER", name="Pioneer Contracting Ltd", short_name="Pioneer",
            organization_type="CONTRACTOR", registration_status=Organization.STATUS_ACTIVE,
        )
        cls.outsider = Organization.objects.create(
            org_code="OTHER", name="Other Co", short_name="Other",
            organization_type="CONTRACTOR", registration_status=Organization.STATUS_ACTIVE,
        )
        cls.sponsor_ua = cls._user("sponsor1", cls.sponsor, "sponsor@example.com")
        cls.contractor_ua = cls._user("contractor1", cls.contractor, "c@example.com")
        cls._user("other1", cls.outsider, "o@example.com")

        task = ProjectTask.objects.create(project_id="ED_T", description="Emurua")
        project = InfraProject.objects.create(
            task=task, owner_org=cls.sponsor, country=cls.ke,
            sector="BUILDINGS", project_type="GOV", county="Narok",
        )
        cls.event = EvaluationEvent.objects.create(
            project=project, ref="ED-AHP/001/2025-2026", description="Emurua Housing",
            issue_date=timezone.now().date(), closing_date=timezone.now() + timedelta(days=30),
            created_by=cls.sponsor_ua,
        )
        cls.listing = TenderListing.objects.create(
            event=cls.event, tender_type=TenderListing.WORKS, visibility=TenderListing.PUBLIC,
            funding_source=TenderListing.GOV, country=cls.ke, county_region="Narok",
            is_published=True, published_at=timezone.now(), created_by=cls.sponsor_ua,
        )
        TenderPreamble.objects.create(
            tender=cls.listing, trade_code="EXCAVATION", title="Excavation and Earthwork",
            body=(
                "Soil Sterilization\n"
                "G. The Contractor will be required to furnish a written guarantee certifying "
                "the treatment against termite infestation.\n"
                "Approval Before Filling\n"
                "B. No fill materials shall be placed before approval has been given by the Architect."
            ),
            sort_order=10, source_page=3,
        )
        BidderRegistration.objects.create(
            tender=cls.listing, organisation=cls.contractor, registered_by=cls.contractor_ua,
        )

    @classmethod
    def _user(cls, username, org, email):
        User = get_user_model()
        u = User.objects.create_user(username=username, password="test-pass-123")
        return UserAccount.objects.create(
            user=u, staff_no=username.upper(), first_name=username, last_name="U",
            designation="X", contact_address="HQ", phone="0", email=email,
            organization=org, access_level=cls.cat,
        )

    def test_generation_creates_cert_hold_and_site_readiness(self):
        n = generate_checkpoints_for_tender(self.listing)
        self.assertGreater(n, 0)
        cats = set(self.listing.checkpoints.values_list("category", flat=True))
        self.assertIn(ComplianceCheckpoint.SITE_READINESS, cats)
        self.assertIn(ComplianceCheckpoint.CERTIFICATE, cats)
        # anti-termite certificate captured from the preamble clause
        self.assertTrue(
            self.listing.checkpoints.filter(
                category=ComplianceCheckpoint.CERTIFICATE,
                title__icontains="Soil Sterilization",
            ).exists()
        )

    def test_register_access_control(self):
        generate_checkpoints_for_tender(self.listing)
        url = reverse("compliance-register", args=[self.listing.pk])

        c = Client(); c.login(username="sponsor1", password="test-pass-123")
        self.assertEqual(c.get(url).status_code, 200)

        c = Client(); c.login(username="contractor1", password="test-pass-123")
        self.assertEqual(c.get(url).status_code, 200)

        c = Client(); c.login(username="other1", password="test-pass-123")
        self.assertEqual(c.get(url).status_code, 302)  # redirected away

    def test_submit_then_signoff_flow(self):
        generate_checkpoints_for_tender(self.listing)
        cp = self.listing.checkpoints.filter(category=ComplianceCheckpoint.CERTIFICATE).first()
        action_url = reverse("compliance-action", args=[self.listing.pk])

        # Contractor submits evidence
        c = Client(); c.login(username="contractor1", password="test-pass-123")
        resp = c.post(action_url, {
            "checkpoint_id": cp.pk, "action": "submit", "certificate_ref": "GUAR-001",
        })
        self.assertEqual(resp.status_code, 302)
        cp.refresh_from_db()
        self.assertEqual(cp.status, ComplianceCheckpoint.STATUS_SUBMITTED)
        self.assertEqual(cp.certificate_ref, "GUAR-001")

        # Contractor cannot approve their own submission
        resp = c.post(action_url, {"checkpoint_id": cp.pk, "action": "approve"})
        cp.refresh_from_db()
        self.assertNotEqual(cp.status, ComplianceCheckpoint.STATUS_APPROVED)

        # Sponsor signs off
        c = Client(); c.login(username="sponsor1", password="test-pass-123")
        resp = c.post(action_url, {"checkpoint_id": cp.pk, "action": "approve", "notes": "ok"})
        cp.refresh_from_db()
        self.assertEqual(cp.status, ComplianceCheckpoint.STATUS_APPROVED)
        self.assertIsNotNone(cp.signed_off_at)

    def test_overdue_property_and_command(self):
        cp = ComplianceCheckpoint.objects.create(
            tender=self.listing, code="X-OVERDUE", title="Overdue item",
            category=ComplianceCheckpoint.HOLD_POINT,
            responsible_user=self.contractor_ua,
            due_date=timezone.now().date() - timedelta(days=2),
        )
        self.assertTrue(cp.is_overdue)
        # command runs without error and stamps overdue_notified_at
        call_command("notify_overdue_checkpoints", "--cooldown-hours", "24")
        cp.refresh_from_db()
        self.assertIsNotNone(cp.overdue_notified_at)
