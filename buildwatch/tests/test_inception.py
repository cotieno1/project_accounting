# -*- coding: utf-8 -*-
from django.test import TestCase
from django.urls import reverse

from accounts.models import UserAccount
from django.contrib.auth import get_user_model

from buildwatch.inception.loader import empty_brief, get_profile, list_profiles, readiness


class InceptionProfileTests(TestCase):
    def test_three_reference_profiles_load(self):
        ids = {p["id"] for p in list_profiles()}
        self.assertIn("infrastructure.dam", ids)
        self.assertIn("ict.telecom_fibre", ids)
        self.assertIn("space.lunar_facility", ids)

    def test_same_gate_ids_across_profiles(self):
        for pid in ("infrastructure.dam", "ict.telecom_fibre", "space.lunar_facility"):
            profile = get_profile(pid)
            gate_ids = [g["id"] for g in profile["gates"]]
            self.assertEqual(
                gate_ids,
                ["concept_approved", "design_direction_approved", "package_approved"],
            )

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


class InceptionWorkspaceViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(username="incept1", password="test-pass-123")
        UserAccount.objects.create(
            user=cls.user,
            staff_no="INCEPT1",
            first_name="In",
            last_name="Cept",
            email="incept1@example.com",
        )

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
