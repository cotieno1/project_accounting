"""Contractor load-PDF-BOQ-into-workspace flow."""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta

from accounts.models import Organization, UserAccount, UserCategory, ProjectTask
from accounts.roles import SENIOR_SITE_MANAGER
from buildwatch.models import (
    Country,
    InfraProject,
    EvaluationEvent,
    TenderListing,
    BidderRegistration,
    BidWorkspace,
)


@override_settings(MEDIA_ROOT="test_media_boq_load")
class LoadPdfBoqTests(TestCase):
    def setUp(self):
        User = get_user_model()
        UserCategory.objects.create(code=SENIOR_SITE_MANAGER, description="SSM", rank=30)
        self.pioneer = Organization.objects.create(
            org_code="PIONEER",
            name="Pioneer Contracting Limited",
            short_name="Pioneer",
            contractor_type=Organization.CONTRACTOR_BUILDING,
            organization_type="CONTRACTOR",
            registration_status=Organization.STATUS_ACTIVE,
        )
        user = User.objects.create_user(username="pioneer1", password="test-pass-123")
        self.ua = UserAccount.objects.create(
            user=user,
            staff_no="P001",
            first_name="P",
            last_name="Staff",
            designation="Site Manager",
            contact_address="Site",
            phone="0",
            email="pioneer@example.com",
            organization=self.pioneer,
            access_level=UserCategory.objects.get(code=SENIOR_SITE_MANAGER),
        )
        country, _ = Country.objects.get_or_create(
            code="KE", defaults={"name": "Kenya"}
        )
        task = ProjectTask.objects.create(
            project_id="SK_004",
            description="Isiolo Stadium Electrical",
        )
        project = InfraProject.objects.create(
            task=task,
            owner_org=self.pioneer,
            country=country,
            sector="BUILDINGS",
            project_type="GOV",
            county="Isiolo",
        )
        event = EvaluationEvent.objects.create(
            project=project,
            ref="SK/004/2025-2026",
            description="Proposed Completion of Isiolo Stadium",
            issue_date=timezone.now().date(),
            closing_date=timezone.now() + timedelta(days=40),
            created_by=self.ua,
        )
        self.listing = TenderListing.objects.create(
            event=event,
            tender_type=TenderListing.WORKS,
            visibility=TenderListing.PUBLIC,
            funding_source=TenderListing.GOV,
            country=country,
            county_region="Isiolo",
            is_published=True,
            published_at=timezone.now(),
            summary="Isiolo electrical works",
            created_by=self.ua,
            boq_input_mode=TenderListing.BOQ_HARDWIRED,
        )
        self.client = Client()

    def test_pioneer_can_load_pdf_boq_into_workspace(self):
        self.client.login(username="pioneer1", password="test-pass-123")
        url = reverse("tender-load-pdf-boq", args=[self.listing.pk])
        response = self.client.post(url)
        self.assertRedirects(
            response,
            reverse("bid-workspace", args=[self.listing.pk]),
            fetch_redirect_response=False,
        )
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.boq_input_mode, TenderListing.BOQ_PDF_AUTO)
        self.assertTrue(
            BidderRegistration.objects.filter(
                tender=self.listing, organisation=self.pioneer
            ).exists()
        )
        self.assertTrue(
            BidWorkspace.objects.filter(
                tender=self.listing, organisation=self.pioneer
            ).exists()
        )
        self.assertGreater(self.listing.boq_packages.count(), 0)

    def test_tender_detail_shows_load_button_for_pioneer(self):
        self.client.login(username="pioneer1", password="test-pass-123")
        response = self.client.get(reverse("tender-detail", args=[self.listing.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Load PDF BOQ into workspace")
        self.assertContains(response, reverse("tender-load-pdf-boq", args=[self.listing.pk]))
