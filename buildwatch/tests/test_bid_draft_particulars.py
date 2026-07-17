"""Draft bid PDF must use the active tender's particulars - never another tender's copy."""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.utils import timezone

from accounts.models import Organization, ProjectTask, UserAccount, UserCategory
from accounts.roles import SENIOR_SITE_MANAGER
from buildwatch.models import (
    BidWorkspace,
    Country,
    EvaluationEvent,
    InfraProject,
    TenderListing,
)
from buildwatch.views_tenders import _bid_pack_context, _bid_pack_particulars


class BidPackParticularsTests(TestCase):
    def setUp(self):
        User = get_user_model()
        UserCategory.objects.create(code=SENIOR_SITE_MANAGER, description="SSM", rank=30)
        self.ke, _ = Country.objects.get_or_create(
            code="KE",
            defaults={"name": "Kenya", "currency_code": "KES", "currency_symbol": "KES"},
        )
        self.employer = Organization.objects.create(
            org_code="SDHUD",
            name="State Department for Housing and Urban Development",
            short_name="Housing",
            contractor_type=Organization.CONTRACTOR_ROADS,
            organization_type="GOV_NATIONAL",
            registration_status=Organization.STATUS_ACTIVE,
            contact_address="P.O Box 30119-00100 Nairobi",
            phone="+254-020-2713833",
        )
        self.bidder = Organization.objects.create(
            org_code="PIONEER",
            name="Pioneer Contracting Limited",
            short_name="Pioneer",
            contractor_type=Organization.CONTRACTOR_BUILDING,
            organization_type="CONTRACTOR",
            registration_status=Organization.STATUS_ACTIVE,
        )
        user = User.objects.create_user(username="p1", password="test-pass-123")
        self.ua = UserAccount.objects.create(
            user=user,
            staff_no="P001",
            first_name="P",
            last_name="One",
            designation="SM",
            contact_address="HQ",
            phone="0",
            email="p@example.com",
            organization=self.bidder,
            access_level=UserCategory.objects.get(code=SENIOR_SITE_MANAGER),
        )
        task = ProjectTask.objects.create(project_id="ED_T", description="Emurua")
        project = InfraProject.objects.create(
            task=task,
            owner_org=self.employer,
            country=self.ke,
            sector="BUILDINGS",
            project_type="GOV",
            county="Narok",
        )
        self.event = EvaluationEvent.objects.create(
            project=project,
            ref="ED-AHP/001/2025-2026",
            description="Proposed Construction of Emurua Dikirr Affordable Housing Project",
            issue_date=timezone.now().date(),
            closing_date=timezone.now() + timedelta(days=30),
            created_by=self.ua,
        )
        self.listing = TenderListing.objects.create(
            event=self.event,
            tender_type=TenderListing.WORKS,
            visibility=TenderListing.PUBLIC,
            funding_source=TenderListing.GOV,
            country=self.ke,
            county_region="Narok",
            is_published=True,
            published_at=timezone.now(),
            summary="AHP housing BOQ Narok",
            works_description="DESCRIPTION OF THE WORKS\nRC foundations and masonry.",
            contract_particulars="CONTRACT PARTICULARS\nB FORM OF CONTRACT\nPPRA Standard Tender Document.",
            created_by=self.ua,
            mr_checklist="",
        )
        self.workspace = BidWorkspace.objects.create(
            tender=self.listing,
            organisation=self.bidder,
            prepared_by=self.ua,
        )

    def test_emurua_particulars_not_isiolo(self):
        p = _bid_pack_particulars(self.listing)
        self.assertIn("Emurua", p["tender_title"])
        self.assertIn("Housing", p["employer_name"])
        self.assertNotIn("Isiolo", p["tender_title"])
        self.assertNotIn("Sports Kenya", p["employer_name"])
        self.assertFalse(p["show_mr_section"])
        self.assertIn("FORM OF CONTRACT", p["contract_particulars"])
        self.assertIn("Emurua", p["source_document"])
        self.assertNotIn("SK/004", p["source_document"])

    def test_bid_pack_context_uses_listing_fields(self):
        request = RequestFactory().get("/tenders/%s/bid/draft.pdf/" % self.listing.pk)
        request.user = self.ua.user
        ctx = _bid_pack_context(request, self.listing, self.workspace, self.bidder, self.ua)
        self.assertEqual(ctx["listing"].pk, self.listing.pk)
        self.assertIn("Emurua", ctx["tender_title"])
        self.assertNotIn("Isiolo", ctx["tender_title"])
        self.assertNotIn("Sports Kenya", ctx["employer_name"])
        self.assertIn("PPRA", ctx["contract_particulars"])
        self.assertFalse(ctx["show_mr_section"])
