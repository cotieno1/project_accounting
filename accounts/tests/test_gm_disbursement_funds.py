"""Regression tests for GM disbursement fund gate and task_id URLs."""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import CEOFundRelease, ProjectBudget, ProjectTask


class GmDisbursementFundsGateTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_superuser(
            username="gm_funds_admin",
            email="gm@test.local",
            password="test-pass-123",
        )
        self.client = Client()
        self.client.login(username="gm_funds_admin", password="test-pass-123")

    def test_malformed_bracket_url_redirects_clean(self):
        ProjectTask.objects.create(project_id="['133']", description="Legacy bracket task")
        url = reverse("gm_aie_disbursement")
        response = self.client.get(url, {"task_id": "['133']"}, follow=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn("task_id=133", response.url)
        self.assertNotIn("%27", response.url)

    def test_no_funds_shows_loud_banner_and_greys_out(self):
        ProjectTask.objects.create(project_id="133", description="Uncommitted task")
        url = reverse("gm_aie_disbursement")
        response = self.client.get(url, {"task_id": "133"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "This Task does not have Any budget approved therefore there No allocated Funds",
        )
        self.assertContains(response, "gm-desk--no-funds")
        self.assertContains(response, "gm-sidebar-tools is-blocked")
        self.assertContains(response, "gm-workspace-tools is-blocked")
        self.assertContains(response, 'id="gmDeskNoFundsEsc"')

    def test_approved_budget_without_release_still_blocked(self):
        task = ProjectTask.objects.create(project_id="FUNDED-001", description="Approved not released")
        ProjectBudget.objects.create(
            task=task,
            budget_label="Major provision",
            version=1,
            is_ceo_approved=True,
            total_authorized_budget=1000,
        )
        url = reverse("gm_aie_disbursement")
        response = self.client.get(url, {"task_id": "FUNDED-001"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "gm-desk--no-funds")

    def test_funds_available_enables_desk(self):
        task = ProjectTask.objects.create(project_id="FUNDED-002", description="Fully funded task")
        budget = ProjectBudget.objects.create(
            task=task,
            budget_label="Major provision",
            version=1,
            is_ceo_approved=True,
            total_authorized_budget=1000,
        )
        CEOFundRelease.objects.create(
            release_number="PV-DSB-2026-0001",
            task=task,
            budget=budget,
            amount=1000,
        )
        url = reverse("gm_aie_disbursement")
        response = self.client.get(url, {"task_id": "FUNDED-002"})
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "gm-desk--no-funds")
