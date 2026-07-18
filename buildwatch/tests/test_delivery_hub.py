"""Project Delivery Hub: award, payment certificates, value-for-money rollup."""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Organization, ProjectTask, UserAccount, UserCategory
from accounts.roles import SENIOR_SITE_MANAGER
from buildwatch.delivery import value_for_money
from buildwatch.models import (
    BidderRegistration,
    Country,
    EvaluationEvent,
    InfraProject,
    PaymentCertificate,
    Submission,
    TenderConsultant,
    TenderListing,
)


class DeliveryHubTests(TestCase):
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
        cls.project = InfraProject.objects.create(
            task=task, owner_org=cls.sponsor, country=cls.ke,
            sector="BUILDINGS", project_type="GOV", county="Narok")
        cls.event = EvaluationEvent.objects.create(
            project=cls.project, ref="ED-AHP/001/2025-2026", description="Emurua Housing",
            issue_date=timezone.now().date(), closing_date=timezone.now() + timedelta(days=30),
            created_by=cls.sponsor_ua)
        cls.listing = TenderListing.objects.create(
            event=cls.event, tender_type=TenderListing.WORKS, visibility=TenderListing.PUBLIC,
            funding_source=TenderListing.GOV, country=cls.ke, county_region="Narok",
            is_published=True, published_at=timezone.now(), created_by=cls.sponsor_ua)
        BidderRegistration.objects.create(
            tender=cls.listing, organisation=cls.contractor, registered_by=cls.contractor_ua)
        Submission.objects.create(
            event=cls.event, submitter_org=cls.contractor, submitted_by=cls.contractor_ua,
            submitted_at=timezone.now(), tender_total=Decimal("100000000"))
        TenderConsultant.objects.create(
            tender=cls.listing, role=TenderConsultant.QS, organisation=cls.sponsor, sort_order=30)

    @classmethod
    def _user(cls, username, org, email):
        User = get_user_model()
        u = User.objects.create_user(username=username, password="test-pass-123")
        return UserAccount.objects.create(
            user=u, staff_no=username.upper(), first_name=username, last_name="U",
            designation="X", contact_address="HQ", phone="0", email=email,
            organization=org, access_level=cls.cat)

    def _sponsor_client(self):
        c = Client(); c.login(username="ckorir", password="test-pass-123"); return c

    def test_hub_renders_on_tender_activity(self):
        resp = self._sponsor_client().get(reverse("my-bids"))
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode("utf-8")
        self.assertIn("Project delivery hub", html)
        self.assertIn("Contract sum", html)
        self.assertIn("Retention held", html)

    def test_record_award_sets_contract_sum_and_flags_submission(self):
        c = self._sponsor_client()
        resp = c.post(reverse("delivery-action", args=[self.listing.pk]), {
            "action": "record_award",
            "awarded_org": self.contractor.org_code,
            "contract_sum": "100000000",
        })
        self.assertEqual(resp.status_code, 302)
        self.project.refresh_from_db()
        self.assertEqual(self.project.contract_value, Decimal("100000000.00"))
        self.assertTrue(Submission.objects.get(event=self.event, submitter_org=self.contractor).is_awarded)

    def test_certificate_lifecycle_and_rollup(self):
        c = self._sponsor_client()
        self.project.contract_value = Decimal("100000000")
        self.project.save(update_fields=["contract_value"])

        # Raise an interim certificate: gross 10m, 10% retention -> net 9m
        c.post(reverse("delivery-action", args=[self.listing.pk]), {
            "action": "add_certificate", "payee_kind": "CONTRACTOR",
            "payee_org": self.contractor.org_code, "cert_type": "INTERIM",
            "gross_amount": "10000000", "retention_pct": "10",
        })
        cert = PaymentCertificate.objects.get(project=self.project)
        self.assertEqual(cert.retention_amount, Decimal("1000000.00"))
        self.assertEqual(cert.net_payable, Decimal("9000000.00"))
        self.assertEqual(cert.status, PaymentCertificate.STATUS_DRAFT)

        # Gov procedure: certify -> requisition order -> payment order
        c.post(reverse("delivery-action", args=[self.listing.pk]),
               {"action": "certify_certificate", "cert_id": cert.pk})
        cert.refresh_from_db()
        self.assertEqual(cert.status, PaymentCertificate.STATUS_CERTIFIED)

        # Payment order cannot be raised before the RO
        c.post(reverse("delivery-action", args=[self.listing.pk]),
               {"action": "raise_payment_order", "cert_id": cert.pk, "paid_reference": "X"})
        cert.refresh_from_db()
        self.assertEqual(cert.status, PaymentCertificate.STATUS_CERTIFIED)

        # Raise the requisition order
        c.post(reverse("delivery-action", args=[self.listing.pk]),
               {"action": "raise_ro", "cert_id": cert.pk})
        cert.refresh_from_db()
        self.assertEqual(cert.status, PaymentCertificate.STATUS_REQUISITIONED)
        self.assertTrue(cert.ro_no.startswith("RO-"))

        # Raise the payment order (transfer of funds)
        c.post(reverse("delivery-action", args=[self.listing.pk]),
               {"action": "raise_payment_order", "cert_id": cert.pk,
                "paid_method": "MPESA", "paid_reference": "MPESA123"})
        cert.refresh_from_db()
        self.assertEqual(cert.status, PaymentCertificate.STATUS_PAID)
        self.assertTrue(cert.pv_no.startswith("PV-"))

        vfm = value_for_money(self.project)
        self.assertEqual(vfm["certified_gross"], Decimal("10000000.00"))
        self.assertEqual(vfm["retention_held"], Decimal("1000000.00"))
        self.assertEqual(vfm["paid_to_date"], Decimal("9000000.00"))
        self.assertEqual(vfm["balance"], Decimal("90000000.00"))
        self.assertEqual(vfm["pct_certified"], 10)

    def test_certificate_pdf_renders(self):
        c = self._sponsor_client()
        cert = PaymentCertificate.objects.create(
            project=self.project, tender=self.listing, payee_kind="CONTRACTOR",
            payee_org=self.contractor, payee_name="Pioneer Contracting Ltd",
            cert_type="INTERIM", gross_amount=Decimal("5000000"), retention_pct=Decimal("10"))
        resp = c.get(reverse("payment-certificate-pdf", args=[self.listing.pk, cert.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")

    def test_contractor_cannot_manage_hub(self):
        c = Client(); c.login(username="pioneer1", password="test-pass-123")
        resp = c.post(reverse("delivery-action", args=[self.listing.pk]), {
            "action": "add_certificate", "payee_kind": "CONTRACTOR",
            "payee_org": self.contractor.org_code, "gross_amount": "1000000",
        })
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(PaymentCertificate.objects.filter(project=self.project).exists())
