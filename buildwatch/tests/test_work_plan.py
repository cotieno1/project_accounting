# -*- coding: utf-8 -*-
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import Organization, UserAccount
from buildwatch.inception.loader import get_profile, list_profiles
from buildwatch.inception.services import approve_concept, get_or_create_workspace, save_workspace_from_post
from buildwatch.models_workplan import ProjectWorkPlan, WorkPlanPhase
from buildwatch.workplan.services import get_or_create_work_plan


class WorkPlanProfileTests(TestCase):
    def setUp(self):
        list_profiles.cache_clear()
        get_profile.cache_clear()

    def test_telecom_work_plan_spans_test_to_commissioning(self):
        pack = get_profile("ict.telecom_operator")["work_plan"]
        kinds = [p["kind"] for p in pack["phases"]]
        self.assertIn("TEST", kinds)
        self.assertIn("COMMISSIONING", kinds)
        codes = {p["id"] for p in pack["phases"]}
        self.assertIn("WAVE_1", codes)
        self.assertTrue(pack["bom_lines"])


class WorkPlanServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(username="wp1", password="test-pass-123")
        cls.org = Organization.objects.create(
            org_code="WPORG",
            name="Work Plan Org",
            short_name="WP Org",
            organization_type="PRIVATE",
            registered_address="Juba",
            contact_address="Juba",
            phone="+211",
            email="wp@test.org",
        )
        cls.ua = UserAccount.objects.create(
            user=cls.user,
            staff_no="WP1",
            first_name="W",
            last_name="P",
            email="wp@test.org",
            designation="Engineer",
            contact_address="Juba",
            phone="+211",
            organization=cls.org,
        )

    def setUp(self):
        list_profiles.cache_clear()
        get_profile.cache_clear()

    def test_approve_concept_seeds_work_plan(self):
        profile = get_profile("ict.telecom_operator")
        inception = get_or_create_workspace(
            org=self.org,
            profile_id="ict.telecom_operator",
            user_account=self.ua,
            title="MTN Rollout",
            seed_project_ref="WP-TEL-001",
        )
        save_workspace_from_post(
            inception=inception,
            profile=profile,
            post={
                "title": "MTN Rollout",
                "lane_mandate": "Coverage",
                "lane_requirements": "Sites",
                "lane_feasibility": "OME",
                "custody_type": "tower_site",
                "custody_status": "ROUTE_IDENTIFIED",
                "funding_type": "commercial",
                "funding_status": "INDICATIVE",
                "funding_envelope": "USD 50M",
            },
            who="wp1",
            user_account=self.ua,
            org=self.org,
        )
        approval, project = approve_concept(
            inception=inception,
            profile=profile,
            who="wp1",
            user_account=self.ua,
        )
        self.assertTrue(hasattr(project, "work_plan"))
        plan = project.work_plan
        self.assertEqual(plan.status, ProjectWorkPlan.STATUS_DRAFT)
        self.assertTrue(plan.phases.filter(kind=WorkPlanPhase.KIND_TEST).exists())
        self.assertTrue(
            plan.phases.filter(kind=WorkPlanPhase.KIND_COMMISSIONING).exists()
        )
        self.assertTrue(plan.bom_lines.exists())
        self.assertEqual(approval.minted_project_id, "WP-TEL-001")

    def test_work_plan_workspace_renders(self):
        profile = get_profile("ict.telecom_operator")
        inception = get_or_create_workspace(
            org=self.org,
            profile_id="ict.telecom_operator",
            user_account=self.ua,
            title="MTN Rollout",
            seed_project_ref="WP-TEL-002",
        )
        save_workspace_from_post(
            inception=inception,
            profile=profile,
            post={
                "title": "MTN Rollout",
                "lane_mandate": "Coverage",
                "lane_requirements": "Sites",
                "lane_feasibility": "OME",
                "custody_type": "tower_site",
                "custody_status": "ROUTE_IDENTIFIED",
                "funding_type": "commercial",
                "funding_status": "INDICATIVE",
                "funding_envelope": "USD 50M",
            },
            who="wp1",
            user_account=self.ua,
            org=self.org,
        )
        _approval, project = approve_concept(
            inception=inception,
            profile=profile,
            who="wp1",
            user_account=self.ua,
        )
        self.client.login(username="wp1", password="test-pass-123")
        response = self.client.get(reverse("work-plan-project", args=[project.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Rollout plan")
        self.assertContains(response, "Programme BOM")
        self.assertContains(response, "Commissioning")
        self.assertContains(response, "Strategic financing envelope")
