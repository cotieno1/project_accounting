"""A project sponsor must only see tenders registered under their own org.

Sponsor A never sees Sponsor B's tenders; contractors and guests see all.
Scoping keys off the owner organisation id (indexed FK) for efficiency.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Organization, ProjectTask, UserAccount, UserCategory
from accounts.roles import SENIOR_SITE_MANAGER
from buildwatch.models import (
    Country,
    EvaluationEvent,
    InfraProject,
    TenderListing,
)


class SponsorTenderScopeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.category = UserCategory.objects.create(
            code=SENIOR_SITE_MANAGER, description="SSM", rank=30
        )
        cls.ke, _ = Country.objects.get_or_create(
            code="KE",
            defaults={"name": "Kenya", "currency_code": "KES", "currency_symbol": "KES"},
        )

        cls.sponsor_a = cls._make_sponsor("SPONA", "Sponsor A Ministry", "SPON-A/001/2025-2026")
        cls.sponsor_b = cls._make_sponsor("SPONB", "Sponsor B Authority", "SPON-B/001/2025-2026")

        # A contractor org (persona = contractor) that should see everything.
        cls.contractor_org = Organization.objects.create(
            org_code="CONTR",
            name="Pioneer Contracting Ltd",
            short_name="Pioneer",
            organization_type="CONTRACTOR",
            registration_status=Organization.STATUS_ACTIVE,
        )
        cls._make_user("contractor1", cls.contractor_org)

    @classmethod
    def _make_sponsor(cls, code, name, ref):
        org = Organization.objects.create(
            org_code=code,
            name=name,
            short_name=code,
            organization_type="GOV_NATIONAL",
            registration_status=Organization.STATUS_ACTIVE,
        )
        ua = cls._make_user(f"{code.lower()}_ps", org)
        task = ProjectTask.objects.create(project_id=f"{code}_PRJ", description=name)
        project = InfraProject.objects.create(
            task=task,
            owner_org=org,
            country=cls.ke,
            sector="BUILDINGS",
            project_type="GOV",
            county="Nairobi",
        )
        event = EvaluationEvent.objects.create(
            project=project,
            ref=ref,
            description=f"{name} works",
            issue_date=timezone.now().date(),
            closing_date=timezone.now() + timedelta(days=30),
            status=EvaluationEvent.STATUS_OPEN,
            created_by=ua,
        )
        TenderListing.objects.create(
            event=event,
            tender_type=TenderListing.WORKS,
            visibility=TenderListing.PUBLIC,
            funding_source=TenderListing.GOV,
            country=cls.ke,
            county_region="Nairobi",
            summary=f"{name} BOQ",
            is_published=True,
            published_at=timezone.now(),
            created_by=ua,
            mr_checklist="",
        )
        org.ref = ref
        return org

    @classmethod
    def _make_user(cls, username, org):
        User = get_user_model()
        user = User.objects.create_user(username=username, password="test-pass-123")
        return UserAccount.objects.create(
            user=user,
            staff_no=username.upper(),
            first_name=username,
            last_name="User",
            designation="Admin",
            contact_address="HQ",
            phone="0",
            email=f"{username}@example.com",
            organization=org,
            access_level=cls.category,
        )

    def _refs(self, response):
        body = response.content.decode()
        return (
            "SPON-A/001/2025-2026" in body,
            "SPON-B/001/2025-2026" in body,
        )

    def test_sponsor_a_sees_only_own_tender(self):
        client = Client()
        client.login(username="spona_ps", password="test-pass-123")
        resp = client.get(reverse("tender-list"))
        self.assertEqual(resp.status_code, 200)
        has_a, has_b = self._refs(resp)
        self.assertTrue(has_a, "Sponsor A should see its own tender")
        self.assertFalse(has_b, "Sponsor A must NOT see Sponsor B's tender")

    def test_sponsor_b_sees_only_own_tender(self):
        client = Client()
        client.login(username="sponb_ps", password="test-pass-123")
        resp = client.get(reverse("tender-list"))
        self.assertEqual(resp.status_code, 200)
        has_a, has_b = self._refs(resp)
        self.assertFalse(has_a, "Sponsor B must NOT see Sponsor A's tender")
        self.assertTrue(has_b, "Sponsor B should see its own tender")

    def test_contractor_sees_all_tenders(self):
        client = Client()
        client.login(username="contractor1", password="test-pass-123")
        resp = client.get(reverse("tender-list"))
        self.assertEqual(resp.status_code, 200)
        has_a, has_b = self._refs(resp)
        self.assertTrue(has_a and has_b, "Contractor should browse all published tenders")

    def test_guest_sees_all_public_tenders(self):
        resp = Client().get(reverse("tender-list"))
        self.assertEqual(resp.status_code, 200)
        has_a, has_b = self._refs(resp)
        self.assertTrue(has_a and has_b, "Guests browse all public tenders")
