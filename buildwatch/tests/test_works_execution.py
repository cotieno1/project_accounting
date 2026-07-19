"""Contractor Works Execution: BOQ -> Task A -> sub-task A-1..n, lifecycle & rollup."""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Organization, ProjectTask, UserAccount, UserCategory
from accounts.roles import SENIOR_SITE_MANAGER
from buildwatch.execution import generate_wbs_for_tender, wbs_overview
from buildwatch.models import (
    BidderRegistration,
    ComplianceCheckpoint,
    Country,
    EvaluationEvent,
    InfraProject,
    TenderListing,
    TenderPreamble,
    WorkSubTask,
)


class WorksExecutionTests(TestCase):
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

        task = ProjectTask.objects.create(project_id="TOMOG-PIONEER-HWF-00026", description="Emurua")
        cls.project = InfraProject.objects.create(
            task=task, owner_org=cls.sponsor, country=cls.ke,
            sector="BUILDINGS", project_type="GOV", county="Narok",
            contract_value=Decimal("100000000"))
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

        pre = TenderPreamble.objects.create(
            tender=cls.listing, trade_code="EXCAVATION", title="Excavation and Earthwork",
            body="Approval before filling ...", sort_order=1, source_page=3)
        # Phase 0 (site readiness) + phase 1 (excavation) => two Task A milestones
        ComplianceCheckpoint.objects.create(
            tender=cls.listing, code="SR-STORE", title="Secure materials storage",
            category=ComplianceCheckpoint.SITE_READINESS, is_mandatory=True, sort_order=1)
        ComplianceCheckpoint.objects.create(
            tender=cls.listing, preamble=pre, code="EX-HOLD", title="Approval before filling",
            category=ComplianceCheckpoint.HOLD_POINT, is_mandatory=True, sort_order=1)
        ComplianceCheckpoint.objects.create(
            tender=cls.listing, preamble=pre, code="EX-CERT", title="Anti-termite guarantee",
            category=ComplianceCheckpoint.CERTIFICATE, is_mandatory=True, sort_order=2)

    @classmethod
    def _user(cls, username, org, email):
        User = get_user_model()
        u = User.objects.create_user(username=username, password="test-pass-123")
        return UserAccount.objects.create(
            user=u, staff_no=username.upper(), first_name=username, last_name="U",
            designation="X", contact_address="HQ", phone="0", email=email,
            organization=org, access_level=cls.cat)

    def _contractor(self):
        c = Client(); c.login(username="pioneer1", password="test-pass-123"); return c

    def _sponsor(self):
        c = Client(); c.login(username="ckorir", password="test-pass-123"); return c

    def test_generate_wbs_from_boq(self):
        created = generate_wbs_for_tender(self.listing, self.contractor_ua)
        self.assertEqual(created, 3)
        self.assertEqual(WorkSubTask.objects.filter(project=self.project).count(), 3)
        # Two Task A milestones (phase 0 + phase 1)
        self.assertEqual(self.project.milestones.count(), 2)
        codes = sorted(WorkSubTask.objects.values_list("code", flat=True))
        self.assertEqual(codes, ["A-1", "B-1", "B-2"])
        # Value distributed from the contract sum across sub-tasks
        ov = wbs_overview(self.project)
        self.assertEqual(ov["totals"]["planned"], Decimal("100000000.00"))
        self.assertTrue(ov["has_wbs"])

    def test_generate_is_idempotent(self):
        generate_wbs_for_tender(self.listing, self.contractor_ua)
        again = generate_wbs_for_tender(self.listing, self.contractor_ua)
        self.assertEqual(again, 0)
        self.assertEqual(WorkSubTask.objects.count(), 3)

    def test_subtask_lifecycle_and_certificate(self):
        generate_wbs_for_tender(self.listing, self.contractor_ua)
        st = WorkSubTask.objects.get(code="A-1")
        url = reverse("works-execution-action", args=[self.listing.pk])
        contractor, sponsor = self._contractor(), self._sponsor()

        contractor.post(url, {"action": "start_subtask", "subtask_id": st.pk})
        st.refresh_from_db(); self.assertEqual(st.status, WorkSubTask.STATUS_IN_PROGRESS)

        contractor.post(url, {"action": "request_inspection", "subtask_id": st.pk})
        st.refresh_from_db(); self.assertEqual(st.status, WorkSubTask.STATUS_INSPECTION)
        self.assertEqual(st.checkpoint.status, ComplianceCheckpoint.STATUS_SUBMITTED)

        # Contractor may NOT approve their own work
        contractor.post(url, {"action": "approve_subtask", "subtask_id": st.pk})
        st.refresh_from_db(); self.assertEqual(st.status, WorkSubTask.STATUS_INSPECTION)

        sponsor.post(url, {"action": "approve_subtask", "subtask_id": st.pk})
        st.refresh_from_db(); self.assertEqual(st.status, WorkSubTask.STATUS_APPROVED)
        self.assertEqual(st.checkpoint.status, ComplianceCheckpoint.STATUS_APPROVED)

        contractor.post(url, {"action": "complete_subtask", "subtask_id": st.pk})
        st.refresh_from_db()
        self.assertEqual(st.status, WorkSubTask.STATUS_DONE)
        self.assertTrue(st.certificate_ref)

        # Earned value now reflects the approved/done sub-task
        ov = wbs_overview(self.project)
        self.assertTrue(ov["totals"]["earned"] > 0)

    def test_page_and_certificate_render(self):
        generate_wbs_for_tender(self.listing, self.contractor_ua)
        c = self._contractor()
        resp = c.get(reverse("works-execution", args=[self.listing.pk]))
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode("utf-8")
        self.assertIn("Executing", html)
        self.assertIn("Open Public Tender Project Task", html)
        self.assertIn("Internal process", html)
        # Governance: external government parties + internal Pioneer
        self.assertIn("Governance", html)
        self.assertIn("QA - Quality Assurance", html)
        self.assertIn("Consulting Engineer (Government)", html)
        self.assertIn("Government Accountant", html)
        self.assertIn("Contractor (Pioneer)", html)
        # Sourcing / best price for outsourced inputs
        self.assertIn("Sourcing", html)
        self.assertIn("best price", html)

        st = WorkSubTask.objects.get(code="A-1")
        st.status = WorkSubTask.STATUS_DONE
        st.certificate_ref = "WSC-TEST-1"
        st.save()
        pdf = c.get(reverse("works-subtask-cert", args=[self.listing.pk, st.pk]))
        self.assertEqual(pdf.status_code, 200)
        self.assertEqual(pdf["Content-Type"], "application/pdf")

    def test_governance_parties(self):
        from buildwatch.execution import governance
        gov = governance(self.project, self.listing)
        roles = [p["role"] for p in gov["external"]]
        self.assertTrue(any("QA" in r for r in roles))
        self.assertTrue(any("PM" in r for r in roles))
        self.assertTrue(any("Consulting Engineer" in r for r in roles))
        self.assertTrue(any("Accountant" in r for r in roles))
        self.assertEqual(len(gov["internal"]), 1)
        self.assertIn("Pioneer", gov["internal"][0]["name"])

    def test_generate_via_view_action(self):
        c = self._contractor()
        resp = c.post(reverse("works-execution-action", args=[self.listing.pk]),
                      {"action": "generate_wbs"})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(WorkSubTask.objects.count(), 3)
