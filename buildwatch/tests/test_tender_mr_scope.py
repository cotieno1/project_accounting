"""Mandatory requirements must be tender-scoped, not a global Kenya dump."""

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
    MandatoryRequirement,
    TenderListing,
)
from buildwatch.views_tenders import _procurement_requirements


class TenderScopedMrTests(TestCase):
    def setUp(self):
        User = get_user_model()
        UserCategory.objects.create(code=SENIOR_SITE_MANAGER, description="SSM", rank=30)
        ke, _ = Country.objects.get_or_create(
            code="KE",
            defaults={"name": "Kenya", "currency_code": "KES", "currency_symbol": "KES"},
        )
        self.ke = ke
        for i, desc in enumerate(
            [
                "Certificate of Incorporation / Business Registration",
                "EPRA Licence - Class B Electrical Installation Works",
            ],
            1,
        ):
            MandatoryRequirement.objects.get_or_create(
                code=f"MR-PROC-KE-{i:02d}",
                defaults={
                    "context": MandatoryRequirement.PROCUREMENT,
                    "country": ke,
                    "description": desc,
                    "is_active": True,
                    "order": i,
                },
            )
        org = Organization.objects.create(
            org_code="OWNER",
            name="Owner Org",
            short_name="Owner",
            contractor_type=Organization.CONTRACTOR_ROADS,
            organization_type="GOV_NATIONAL",
            registration_status=Organization.STATUS_ACTIVE,
        )
        user = User.objects.create_user(username="owner1", password="test-pass-123")
        ua = UserAccount.objects.create(
            user=user,
            staff_no="O001",
            first_name="O",
            last_name="Wner",
            designation="Admin",
            contact_address="HQ",
            phone="0",
            email="owner@example.com",
            organization=org,
            access_level=UserCategory.objects.get(code=SENIOR_SITE_MANAGER),
        )
        task = ProjectTask.objects.create(project_id="ED_TEST", description="Housing")
        project = InfraProject.objects.create(
            task=task,
            owner_org=org,
            country=ke,
            sector="BUILDINGS",
            project_type="GOV",
            county="Narok",
        )
        event = EvaluationEvent.objects.create(
            project=project,
            ref="ED-AHP/TEST/2025-2026",
            description="Emurua test housing",
            issue_date=timezone.now().date(),
            closing_date=timezone.now() + timedelta(days=30),
            status=EvaluationEvent.STATUS_OPEN,
            created_by=ua,
        )
        self.listing = TenderListing.objects.create(
            event=event,
            tender_type=TenderListing.WORKS,
            visibility=TenderListing.PUBLIC,
            funding_source=TenderListing.GOV,
            country=ke,
            county_region="Narok",
            summary="Housing BOQ",
            is_published=True,
            published_at=timezone.now(),
            created_by=ua,
            mr_checklist="",
        )
        self.client = Client()

    def test_emurua_without_checklist_has_no_mrs(self):
        self.assertEqual(list(_procurement_requirements(self.listing)), [])
        response = self.client.get(reverse("tender-detail", args=[self.listing.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "EPRA Licence")
        self.assertNotContains(response, "Mandatory Requirements")

    def test_isiolo_pack_only_when_checklist_set(self):
        self.listing.mr_checklist = TenderListing.MR_CHECKLIST_KE_ELECTRICAL_RFQ
        self.listing.save(update_fields=["mr_checklist"])
        reqs = list(_procurement_requirements(self.listing))
        self.assertTrue(reqs)
        self.assertTrue(all(r.code.startswith("MR-PROC-KE-") for r in reqs))
        response = self.client.get(reverse("tender-detail", args=[self.listing.pk]))
        self.assertContains(response, "Mandatory Requirements")
        self.assertContains(response, "EPRA Licence")
