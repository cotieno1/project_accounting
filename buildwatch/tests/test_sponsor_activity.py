"""my-bids is persona-aware: sponsor sees Tender Activity, contractor sees My Bids."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Organization, ProjectTask, UserAccount, UserCategory
from accounts.roles import SENIOR_SITE_MANAGER
from buildwatch.models import (
    BidderRegistration,
    Country,
    EvaluationEvent,
    InfraProject,
    TenderConsultant,
    TenderListing,
)


class SponsorActivityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.cat = UserCategory.objects.create(code=SENIOR_SITE_MANAGER, description="SSM", rank=30)
        cls.ke, _ = Country.objects.get_or_create(
            code="KE", defaults={"name": "Kenya", "currency_code": "KES", "currency_symbol": "KES"})
        cls.sponsor = Organization.objects.create(
            org_code="SDHUD", name="State Dept Housing", short_name="Housing",
            organization_type="GOV_NATIONAL", registration_status=Organization.STATUS_ACTIVE)
        cls.contractor = Organization.objects.create(
            org_code="PIONEER", name="Pioneer Contracting Ltd", short_name="Pioneer",
            organization_type="CONTRACTOR", registration_status=Organization.STATUS_ACTIVE)
        cls.sponsor_ua = cls._user("ckorir", cls.sponsor, "ps@example.com")
        cls.contractor_ua = cls._user("pioneer1", cls.contractor, "c@example.com")

        task = ProjectTask.objects.create(project_id="ED_T", description="Emurua")
        project = InfraProject.objects.create(
            task=task, owner_org=cls.sponsor, country=cls.ke,
            sector="BUILDINGS", project_type="GOV", county="Narok")
        cls.event = EvaluationEvent.objects.create(
            project=project, ref="ED-AHP/001/2025-2026", description="Emurua Housing",
            issue_date=timezone.now().date(), closing_date=timezone.now() + timedelta(days=30),
            created_by=cls.sponsor_ua)
        cls.listing = TenderListing.objects.create(
            event=cls.event, tender_type=TenderListing.WORKS, visibility=TenderListing.PUBLIC,
            funding_source=TenderListing.GOV, country=cls.ke, county_region="Narok",
            is_published=True, published_at=timezone.now(), created_by=cls.sponsor_ua)
        BidderRegistration.objects.create(
            tender=cls.listing, organisation=cls.contractor, registered_by=cls.contractor_ua)
        TenderConsultant.objects.create(
            tender=cls.listing, role=TenderConsultant.ARCHITECT, organisation=cls.sponsor,
            address="P.O Box 30119 - 00100, NAIROBI", sort_order=20)

    @classmethod
    def _user(cls, username, org, email):
        User = get_user_model()
        u = User.objects.create_user(username=username, password="test-pass-123")
        return UserAccount.objects.create(
            user=u, staff_no=username.upper(), first_name=username, last_name="U",
            designation="X", contact_address="HQ", phone="0", email=email,
            organization=org, access_level=cls.cat)

    def test_sponsor_sees_tender_activity_not_workspace(self):
        c = Client(); c.login(username="ckorir", password="test-pass-123")
        resp = c.get(reverse("my-bids"))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "tenders/sponsor_activity.html")
        html = resp.content.decode("utf-8")
        self.assertIn("Tender Activity", html)
        self.assertIn("Companies bidding", html)
        self.assertIn("Consultant team", html)
        self.assertIn("Pioneer Contracting Ltd", html)   # the bidder is listed
        self.assertIn("Architect", html)                  # consultant role shown
        self.assertNotIn("Bid Workspaces", html)          # no bidder-workspace content

    def test_contractor_still_sees_my_bids(self):
        c = Client(); c.login(username="pioneer1", password="test-pass-123")
        resp = c.get(reverse("my-bids"))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "tenders/my_bids.html")
