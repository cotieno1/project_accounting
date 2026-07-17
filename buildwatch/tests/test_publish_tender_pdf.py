"""Publish new tender from local BOQ PDF."""

from datetime import timedelta
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import Organization, UserAccount, UserCategory
from accounts.roles import USER_ADMIN
from buildwatch.models import Country, EvaluationEvent, TenderListing


@override_settings(MEDIA_ROOT="test_media_publish_tender")
class PublishTenderPdfTests(TestCase):
    def setUp(self):
        User = get_user_model()
        UserCategory.objects.create(code=USER_ADMIN, description="Admin", rank=100)
        self.employer = Organization.objects.create(
            org_code="SDHUD",
            name="State Department Housing",
            short_name="Housing",
            contractor_type=Organization.CONTRACTOR_ROADS,
            organization_type="GOV_NATIONAL",
            registration_status=Organization.STATUS_ACTIVE,
        )
        Country.objects.get_or_create(
            code="KE",
            defaults={"name": "Kenya", "currency_code": "KES", "currency_symbol": "KES"},
        )
        admin = User.objects.create_user(username="publisher", password="test-pass-123")
        UserAccount.objects.create(
            user=admin,
            staff_no="ADM99",
            first_name="Pub",
            last_name="Lisher",
            designation="Publisher",
            contact_address="HQ",
            phone="0",
            email="publisher@example.com",
            organization=self.employer,
            access_level=UserCategory.objects.get(code=USER_ADMIN),
        )
        self.client = Client()

    def test_upload_new_tender_pdf_from_local_drive(self):
        self.client.login(username="publisher", password="test-pass-123")
        pdf = SimpleUploadedFile(
            "emurua_dikirr_ahp_priced_boq.pdf",
            b"%PDF-1.4 fake emurua boq content",
            content_type="application/pdf",
        )
        closing = (timezone.now() + timedelta(days=40)).strftime("%Y-%m-%dT%H:%M")
        response = self.client.post(
            reverse("tender-publish"),
            {
                "create_new_project": "1",
                "new_project_code": "ED_AHP_TEST",
                "ref": "ED-AHP/TEST/2025-2026",
                "description": "Emurua Dikirr Affordable Housing Project BOQ",
                "summary": "Narok County AHP priced BOQ",
                "tender_type": TenderListing.WORKS,
                "visibility": TenderListing.PUBLIC,
                "funding_source": TenderListing.GOV,
                "country": "KE",
                "county_region": "Narok County",
                "sector": "BUILDINGS",
                "issue_date": timezone.now().date().isoformat(),
                "closing_date": closing,
                "currency": "KES",
                "publish_now": "1",
                "boq_document": pdf,
            },
        )
        listing = TenderListing.objects.filter(event__ref="ED-AHP/TEST/2025-2026").first()
        self.assertIsNotNone(listing)
        self.assertTrue(listing.is_published)
        self.assertTrue(bool(listing.boq_document))
        self.assertEqual(listing.event.status, EvaluationEvent.STATUS_OPEN)
        self.assertRedirects(
            response,
            reverse("tender-detail", args=[listing.pk]),
            fetch_redirect_response=False,
        )

    def test_tender_list_shows_upload_cta_for_publisher(self):
        self.client.login(username="publisher", password="test-pass-123")
        response = self.client.get(reverse("tender-list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Upload new tender (PDF)")
        self.assertContains(response, reverse("tender-publish"))
