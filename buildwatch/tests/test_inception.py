# -*- coding: utf-8 -*-
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import Organization, UserAccount
from buildwatch.inception.loader import (
    empty_brief,
    get_profile,
    list_profiles,
    readiness,
)
from buildwatch.inception.services import approve_concept, get_or_create_workspace, save_workspace_from_post
from buildwatch.models_inception import InceptionApproval, ProjectInception


class InceptionProfileTests(TestCase):
    def setUp(self):
        list_profiles.cache_clear()
        get_profile.cache_clear()

    def test_reference_profiles_load(self):
        ids = {p["id"] for p in list_profiles()}
        self.assertIn("infrastructure.dam", ids)
        self.assertIn("ict.telecom_fibre", ids)
        self.assertIn("ict.telecom_operator", ids)
        self.assertIn("space.lunar_facility", ids)
        self.assertIn("buildings.works", ids)

    def test_same_gate_ids_across_profiles(self):
        for pid in (
            "infrastructure.dam",
            "ict.telecom_fibre",
            "ict.telecom_operator",
            "space.lunar_facility",
            "buildings.works",
        ):
            profile = get_profile(pid)
            gate_ids = [g["id"] for g in profile["gates"]]
            self.assertEqual(
                gate_ids,
                ["concept_approved", "design_direction_approved", "package_approved"],
            )

    def test_telecom_operator_profile_covers_towers_and_bts(self):
        profile = get_profile("ict.telecom_operator")
        custody_ids = {c["id"] for c in profile["custody_types"]}
        self.assertIn("tower_site", custody_ids)
        self.assertIn("bts_compound", custody_ids)
        text = " ".join(
            " ".join(lane.get("prompts") or []) for lane in profile["lanes"]
        ).lower()
        self.assertIn("tower", text)
        self.assertIn("base station", text)
        self.assertIn("fibre", text)

    def test_buildings_pack_has_elemental_budget_lines(self):
        profile = get_profile("buildings.works")
        codes = {row["id"] for row in profile.get("budget_lines") or []}
        self.assertIn("substructure", codes)
        self.assertIn("consultant_fees", codes)
        self.assertIn("contingency", codes)

    def test_concept_readiness_requires_lanes_custody_funding(self):
        profile = get_profile("infrastructure.dam")
        brief = empty_brief(profile)
        self.assertFalse(readiness(brief, profile)["concept_ready"])
        for lid in ("mandate", "requirements", "feasibility"):
            brief["lanes"][lid]["body"] = "draft"
        brief["custody"] = {"type_id": "catchment_rights", "status": "ROUTE_IDENTIFIED"}
        brief["funding"] = {
            "type_id": "exchequer",
            "status": "INDICATIVE",
            "envelope": "USD 400M",
        }
        self.assertTrue(readiness(brief, profile)["concept_ready"])


class InceptionPersistenceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(username="incept1", password="test-pass-123")
        cls.org = Organization.objects.create(
            org_code="TESTORG",
            name="Test Sponsor Org",
            short_name="TestOrg",
            organization_type="PRIVATE",
            registered_address="Nairobi",
            contact_address="Nairobi",
            phone="+254",
            email="ops@test.org",
        )
        cls.ua = UserAccount.objects.create(
            user=cls.user,
            staff_no="INCEPT1",
            first_name="In",
            last_name="Cept",
            email="incept1@example.com",
            designation="Engineer",
            contact_address="Nairobi",
            phone="+254",
            organization=cls.org,
        )

    def setUp(self):
        list_profiles.cache_clear()
        get_profile.cache_clear()

    def test_approve_mints_infra_project(self):
        profile = get_profile("buildings.works")
        inception = get_or_create_workspace(
            org=self.org,
            profile_id="buildings.works",
            user_account=self.ua,
            title="Test Housing Estate",
            seed_project_ref="TEST-HOUS-001",
        )
        post = {
            "title": "Test Housing Estate",
            "lane_mandate": "Need housing for staff",
            "lane_requirements": "120 units",
            "lane_feasibility": "OME ok",
            "custody_type": "freehold",
            "custody_status": "ROUTE_IDENTIFIED",
            "custody_owner": "County",
            "custody_route": "Title search",
            "funding_type": "exchequer",
            "funding_status": "INDICATIVE",
            "funding_envelope": "KES 2B",
            "funding_note": "Vote head",
            "budget_line_substructure": "1000000",
        }
        save_workspace_from_post(
            inception=inception,
            profile=profile,
            post=post,
            who="incept1",
            user_account=self.ua,
            org=self.org,
        )
        inception.refresh_from_db()
        self.assertEqual(inception.stage, ProjectInception.STAGE_DOCUMENTED)

        approval, project = approve_concept(
            inception=inception,
            profile=profile,
            who="incept1",
            user_account=self.ua,
            comments="Proceed",
        )
        inception.refresh_from_db()
        self.assertEqual(approval.action, InceptionApproval.APPROVED)
        self.assertEqual(approval.minted_project_id, "TEST-HOUS-001")
        self.assertEqual(inception.stage, ProjectInception.STAGE_DESIGN)
        self.assertEqual(project.task_id, "TEST-HOUS-001")
        self.assertTrue(inception.concept_budget.is_approved)
        self.assertEqual(
            inception.concept_budget.lines.get(code="substructure").amount,
            1000000,
        )


class InceptionWorkspaceViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(username="incept1", password="test-pass-123")
        cls.org = Organization.objects.create(
            org_code="VIEWORG",
            name="View Org",
            short_name="ViewOrg",
            organization_type="PRIVATE",
            registered_address="Nairobi",
            contact_address="Nairobi",
            phone="+254",
            email="view@test.org",
        )
        UserAccount.objects.create(
            user=cls.user,
            staff_no="INCEPTV1",
            first_name="In",
            last_name="Cept",
            email="incept1@example.com",
            designation="Engineer",
            contact_address="Nairobi",
            phone="+254",
            organization=cls.org,
        )

    def setUp(self):
        list_profiles.cache_clear()
        get_profile.cache_clear()

    def test_workspace_requires_login(self):
        response = self.client.get(reverse("inception-workspace"))
        self.assertEqual(response.status_code, 302)

    def test_workspace_renders_product_definition(self):
        self.client.login(username="incept1", password="test-pass-123")
        response = self.client.get(reverse("inception-workspace"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "BuildWatch Inception is an open collaboration")
        self.assertContains(response, "Living brief")
        self.assertContains(response, "Asset / site custody")
        self.assertContains(response, "Resource commitment")
        self.assertContains(response, "Main Dashboard")
        self.assertContains(response, "Log out")
        self.assertNotContains(response, "Projects Status")
        self.assertNotContains(response, "Tender activity")
        self.assertNotContains(response, ">Tenders <")
        # Persisted inception identity
        self.assertContains(response, "INC-")

    def test_mtn_tenant_defaults_telecom_profile_and_title(self):
        org = Organization.objects.create(
            org_code="MTNSS",
            name="MTN South Sudan",
            short_name="MTN South Sudan",
            organization_type="PRIVATE",
            registered_address="Juba",
            contact_address="Juba",
            phone="+211",
            email="ops@mtn.com.ss",
        )
        ua = UserAccount.objects.get(user=self.user)
        ua.organization = org
        ua.save(update_fields=["organization"])

        self.client.login(username="incept1", password="test-pass-123")
        response = self.client.get(reverse("inception-workspace"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "MTN South Sudan")
        self.assertContains(response, "MTN-SSD-TEL-001")
        self.assertContains(
            response, "MTN South Sudan - Telecommunications Network Programme"
        )
        self.assertContains(response, "Telecom operator network")
        self.assertContains(response, "base stations")
        self.assertContains(response, "transmission towers")
        self.assertContains(response, "Concept budget")
        self.assertNotContains(response, "Ministry of Works")
        self.assertNotContains(response, "ckorir")
