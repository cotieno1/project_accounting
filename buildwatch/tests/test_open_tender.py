# ============================================================================
# Tests: Open Tender Financial + Public Tender Internal Fin Ops
# ============================================================================
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Organization, ProjectTask, UserAccount
from buildwatch.models import (
    BidWorkspace,
    EvaluationEvent,
    InfraProject,
    PublicTenderProfile,
    SubTaskResource,
    TenderBoqPackage,
    TenderListing,
    WorkspaceBillPrice,
    WorkSubTask,
)
from buildwatch.open_tender import (
    generate_subtasks_from_boq,
    public_task_ids,
    set_resource_phases,
)


User = get_user_model()


class OpenTenderFinOpsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.sponsor_org = Organization.objects.create(
            org_code="SDHUD-OT", name="Ministry of Lands Test", short_name="Housing",
            organization_type="GOV_NATIONAL",
            registration_status=Organization.STATUS_ACTIVE,
        )
        cls.contractor_org = Organization.objects.create(
            org_code="PIONEER-OT", name="Pioneer Test", short_name="Pioneer",
            organization_type="CONTRACTOR",
            registration_status=Organization.STATUS_ACTIVE,
        )
        cls.user = User.objects.create_user(username="pioneer_ot", password="pass")
        cls.ua = UserAccount.objects.create(
            user=cls.user,
            staff_no="PIONEER-OT-1",
            first_name="Site",
            last_name="Engineer",
            designation="Snr Site Engineer",
            contact_address="HQ",
            phone="0700000000",
            email="pioneer_ot@example.com",
            organization=cls.contractor_org,
        )
        close_task = ProjectTask.objects.create(
            project_id="CLOSE-TASK-001", description="Existing close tender task",
        )
        cls.project = InfraProject.objects.create(
            task=close_task,
            owner_org=cls.sponsor_org,
            sector="BUILDINGS",
            project_type="GOV",
            county="Narok",
        )
        cls.event = EvaluationEvent.objects.create(
            ref="ED-AHP/TEST/001",
            description="Emurua test tender",
            project=cls.project,
            status="OPEN",
            issue_date=timezone.now().date(),
            closing_date=timezone.now() + timedelta(days=30),
            created_by=cls.ua,
        )
        cls.listing = TenderListing.objects.create(
            event=cls.event,
            visibility="PUBLIC",
            tender_type="WORKS",
            is_published=True,
            created_by=cls.ua,
        )
        TenderBoqPackage.objects.create(
            tender=cls.listing, code="BA-B01-E01", title="Substructure", sort_order=1,
        )
        TenderBoqPackage.objects.create(
            tender=cls.listing, code="BA-B01-E02", title="Concrete Work", sort_order=2,
        )
        # Pilot packages: R.C Frame (concrete) + Internal Finishes (tiling)
        cls.pkg_rc = TenderBoqPackage.objects.create(
            tender=cls.listing, code="BA-B04-E02",
            title="Block A / El 2 R.C FRAME", sort_order=10,
        )
        cls.pkg_fin = TenderBoqPackage.objects.create(
            tender=cls.listing, code="BA-B04-E07",
            title="Block A / El 7 INTERNAL FINISHES", sort_order=11,
        )
        from buildwatch.models import TenderBoqLine
        TenderBoqLine.objects.create(
            package=cls.pkg_rc, bill_ref="E02-A", description="Columns",
            unit="CM", quantity=Decimal("10"), sort_order=1,
        )
        TenderBoqLine.objects.create(
            package=cls.pkg_rc, bill_ref="E02-E", description="130mm thick suspended slabs",
            unit="SM", quantity=Decimal("100"), sort_order=2,
        )
        TenderBoqLine.objects.create(
            package=cls.pkg_fin, bill_ref="E07-C",
            description="Supply and Fix ceramic wall tiles on prepared backings",
            unit="SM", quantity=Decimal("50"), sort_order=1,
        )
        TenderBoqLine.objects.create(
            package=cls.pkg_fin, bill_ref="E07-F2",
            description="Supply and Fix Ceramic tiles; on prepared bed floors",
            unit="SM", quantity=Decimal("40"), sort_order=2,
        )
        TenderBoqLine.objects.create(
            package=cls.pkg_fin, bill_ref="E07-G",
            description="Ditto Non Slip Ceramic Tiles",
            unit="SM", quantity=Decimal("20"), sort_order=3,
        )
        cls.ws = BidWorkspace.objects.create(
            tender=cls.listing,
            organisation=cls.contractor_org,
            prepared_by=cls.ua,
            selected_package_codes=["BA-B01-E01", "BA-B01-E02"],
            pricing_complete=True,
            total_bid_amount=Decimal("1500000"),
        )
        WorkspaceBillPrice.objects.create(
            workspace=cls.ws, bill_ref="1", package_code="BA-B01-E01",
            description="Foundations", quantity=Decimal("1"), unit_rate=Decimal("1000000"),
        )
        WorkspaceBillPrice.objects.create(
            workspace=cls.ws, bill_ref="2", package_code="BA-B01-E02",
            description="RC works", quantity=Decimal("1"), unit_rate=Decimal("500000"),
        )

    def _client(self):
        c = Client()
        c.login(username="pioneer_ot", password="pass")
        return c

    def test_create_public_profile_and_boq_subtasks(self):
        c = self._client()
        resp = c.post(reverse("open-tender-from-listing", args=[self.listing.pk]))
        self.assertEqual(resp.status_code, 302)
        profile = PublicTenderProfile.objects.get(tender=self.listing)
        self.assertEqual(profile.category, PublicTenderProfile.CATEGORY_PUBLIC_TENDER)
        self.assertTrue(profile.task_id.startswith("PT-"))
        # Dedicated task - Close Tender task untouched
        self.assertNotEqual(profile.task_id, "CLOSE-TASK-001")
        self.assertIn(profile.task_id, public_task_ids())

        boq = list(profile.subtasks.filter(kind=WorkSubTask.KIND_BOQ))
        internal = list(profile.subtasks.filter(kind=WorkSubTask.KIND_INTERNAL))
        self.assertEqual(len(boq), 2)
        self.assertGreaterEqual(len(internal), 1)
        self.assertEqual(
            sum((s.planned_value for s in boq), Decimal("0")),
            Decimal("1500000.00"),
        )
        # Idempotent refresh adds nothing
        self.assertEqual(generate_subtasks_from_boq(profile), 0)

    def test_open_tender_dashboard_renders(self):
        task = ProjectTask.objects.create(project_id="PT-TEST-1", description="Public")
        PublicTenderProfile.objects.create(
            task=task, tender=self.listing, category="PUBLIC_TENDER",
            contractor_org=self.contractor_org,
        )
        c = self._client()
        resp = c.get(reverse("open-tender-dashboard"))
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode("utf-8")
        self.assertIn("Open Tender", html)
        self.assertIn("ED-AHP/TEST/001", html)

    def test_phased_resource_split(self):
        task = ProjectTask.objects.create(project_id="PT-TEST-2", description="Public")
        profile = PublicTenderProfile.objects.create(
            task=task, tender=self.listing, category="PUBLIC_TENDER",
            contractor_org=self.contractor_org,
        )
        st = WorkSubTask.objects.create(
            profile=profile, project=self.project, tender=self.listing,
            kind=WorkSubTask.KIND_INTERNAL, code="INT-02",
            name="Site clearing", seq=1,
        )
        c = self._client()
        resp = c.post(reverse("public-tender-fin-ops-action", args=[profile.pk]), {
            "action": "add_resource",
            "subtask_id": st.pk,
            "name": "Cement",
            "resource_kind": "MATERIAL",
            "unit": "bags",
            "total_qty": "10000",
        })
        self.assertEqual(resp.status_code, 302)
        resource = SubTaskResource.objects.get(subtask=st, name="Cement")
        self.assertEqual(resource.total_qty, Decimal("10000"))

        phases = set_resource_phases(resource, [Decimal("5000"), Decimal("2500"), Decimal("2500")])
        self.assertEqual(len(phases), 3)
        self.assertEqual(sum(p.qty for p in phases), Decimal("10000"))

        resp = c.get(reverse("public-tender-fin-ops", args=[profile.pk]))
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode("utf-8")
        self.assertIn("Public Tender Internal Fin Ops", html)
        self.assertIn("Cement", html)
        self.assertIn("5000", html)

    def test_close_tender_excludes_public_tasks(self):
        from accounts.views import fin_mgmt_ops_view
        from django.test import RequestFactory

        task = ProjectTask.objects.create(project_id="PT-EXCL", description="Public only")
        PublicTenderProfile.objects.create(
            task=task, tender=self.listing, category="PUBLIC_TENDER",
            contractor_org=self.contractor_org,
        )
        rf = RequestFactory()
        req = rf.get("/ops-dashboard/")
        req.user = self.user
        req.session = {}
        # Attach messages middleware bits minimally via client instead
        c = self._client()
        resp = c.get(reverse("ops_dashboard"))
        self.assertEqual(resp.status_code, 200)
        # Public task must not appear in Close Tender task list context
        tasks = list(resp.context["tasks"].values_list("project_id", flat=True))
        self.assertNotIn("PT-EXCL", tasks)
        self.assertIn("CLOSE-TASK-001", tasks)

    def test_completion_requires_authorization_trail(self):
        task = ProjectTask.objects.create(project_id="PT-TEST-3", description="Public")
        profile = PublicTenderProfile.objects.create(
            task=task, tender=self.listing, category="PUBLIC_TENDER",
            contractor_org=self.contractor_org,
        )
        st = WorkSubTask.objects.create(
            profile=profile, project=self.project, tender=self.listing,
            kind=WorkSubTask.KIND_BOQ, code="BOQ-01", name="Substructure",
            package_code="BA-B01-E01", planned_value=Decimal("100"),
        )
        c = self._client()
        url = reverse("open-tender-action", args=[profile.pk])
        # Strict FS gate order on same sub-task
        c.post(url, {"action": "start_subtask", "subtask_id": st.pk})
        st.refresh_from_db()
        self.assertEqual(st.status, WorkSubTask.STATUS_IN_PROGRESS)

        # Cannot skip to authorize
        c.post(url, {"action": "authorize_subtask", "subtask_id": st.pk})
        st.refresh_from_db()
        self.assertEqual(st.status, WorkSubTask.STATUS_IN_PROGRESS)

        c.post(url, {"action": "request_inspection", "subtask_id": st.pk})
        c.post(url, {
            "action": "signoff_subtask", "subtask_id": st.pk,
            "signoff_authority": "MoW Structural Engineer",
        })
        c.post(url, {
            "action": "certify_subtask", "subtask_id": st.pk,
            "certified_products": "Bamburi CEM I 42.5",
            "proof_notes": "DN-001 + cube tests",
        })
        c.post(url, {"action": "authorize_subtask", "subtask_id": st.pk})
        c.post(url, {"action": "mark_payable", "subtask_id": st.pk})
        c.post(url, {"action": "mark_paid", "subtask_id": st.pk})
        st.refresh_from_db()
        self.assertEqual(st.status, WorkSubTask.STATUS_PAID)
        self.assertTrue(st.is_done)
        self.assertTrue(st.certificate_ref)
        self.assertIn("Bamburi", st.certified_products)
        self.assertIn("DN-001", st.proof_notes)
        self.assertEqual(st.signoff_authority, "MoW Structural Engineer")

    def test_fs_dependency_blocks_parallel_start(self):
        from buildwatch.models import ActivityDependency

        task = ProjectTask.objects.create(project_id="PT-FS-1", description="Public")
        profile = PublicTenderProfile.objects.create(
            task=task, tender=self.listing, category="PUBLIC_TENDER",
            contractor_org=self.contractor_org,
        )
        a = WorkSubTask.objects.create(
            profile=profile, project=self.project, tender=self.listing,
            kind=WorkSubTask.KIND_BOQ, code="A", name="First", planned_value=Decimal("10"),
        )
        b = WorkSubTask.objects.create(
            profile=profile, project=self.project, tender=self.listing,
            kind=WorkSubTask.KIND_BOQ, code="B", name="Second", planned_value=Decimal("10"),
        )
        ActivityDependency.objects.create(
            profile=profile, predecessor_subtask=a, successor_subtask=b,
            required_status=WorkSubTask.STATUS_AUTHORIZED,
        )
        c = self._client()
        url = reverse("open-tender-action", args=[profile.pk])
        c.post(url, {"action": "start_subtask", "subtask_id": b.pk})
        b.refresh_from_db()
        self.assertEqual(b.status, WorkSubTask.STATUS_PLANNED)

        # Without FS link, parallel start would work; A can start freely
        c.post(url, {"action": "start_subtask", "subtask_id": a.pk})
        a.refresh_from_db()
        self.assertEqual(a.status, WorkSubTask.STATUS_IN_PROGRESS)

    def test_activities_and_activity_based_budget(self):
        from buildwatch.models import OpenTenderActivity
        from buildwatch.open_tender import generate_activities_from_boq_lines

        task = ProjectTask.objects.create(project_id="PT-ACT-1", description="Public")
        profile = PublicTenderProfile.objects.create(
            task=task, tender=self.listing, category="PUBLIC_TENDER",
            contractor_org=self.contractor_org,
        )
        result = generate_activities_from_boq_lines(profile, with_draft_budget=True)
        self.assertGreaterEqual(result["activities"], 5)
        self.assertGreater(result["budget_lines"], 0)

        tile = OpenTenderActivity.objects.filter(code="E07-C").first()
        self.assertIsNotNone(tile)
        self.assertEqual(tile.measure_unit, "m2")
        self.assertIn("wet areas", tile.location_hint.lower())
        self.assertGreater(tile.budget_lines.count(), 0)
        kinds = set(tile.budget_lines.values_list("kind", flat=True))
        self.assertIn("MATERIAL", kinds)
        self.assertIn("LABOUR", kinds)

        col = OpenTenderActivity.objects.filter(code="E02-A").first()
        self.assertIsNotNone(col)
        self.assertEqual(col.measure_unit, "m3")
        self.assertEqual(col.location_hint, "Columns")

        c = self._client()
        resp = c.post(reverse("open-tender-action", args=[profile.pk]), {
            "action": "generate_activities",
        })
        self.assertEqual(resp.status_code, 302)
        detail = c.get(reverse("open-tender-detail", args=[profile.pk]))
        self.assertEqual(detail.status_code, 200)
        html = detail.content.decode("utf-8")
        self.assertIn("activity-based budget", html)
        self.assertIn("ceramic wall tiles", html.lower())
        self.assertIn("Columns", html)

    def test_project_wbs_page(self):
        c = self._client()
        resp = c.get(reverse("tender-project-wbs", args=[self.listing.pk]))
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode("utf-8")
        self.assertIn("Complete Project WBS", html)
        self.assertIn("BA-B04-E02", html)
        self.assertIn("Columns", html)
        self.assertIn("ceramic wall tiles", html.lower())
