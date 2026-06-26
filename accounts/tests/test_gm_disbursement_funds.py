"""Regression tests for GM disbursement fund gate and task_id URLs."""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import CEOFundRelease, LPOTransaction, ProjectBudget, ProjectTask


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

    def test_uncommitted_task_is_blocked(self):
        ProjectTask.objects.create(project_id="133", description="Uncommitted task")
        url = reverse("gm_aie_disbursement")
        response = self.client.get(url, {"task_id": "133"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "gm-desk--no-funds")
        self.assertContains(response, "no provision budget committed yet")

    def test_major_lpo_task_not_blocked_without_fund_release(self):
        task = ProjectTask.objects.create(project_id="MAJOR-LPO-001", description="Major with LPO")
        ProjectBudget.objects.create(
            task=task,
            budget_label="Major provision",
            version=1,
            is_ceo_approved=False,
            total_authorized_budget=5000,
        )
        LPOTransaction.objects.create(
            lpo_no="LPO-MAJOR-LPO-001-001",
            project_task=task,
            total_amount=1200,
        )
        url = reverse("gm_aie_disbursement")
        response = self.client.get(url, {"task_id": "MAJOR-LPO-001"})
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "gm-desk--no-funds")
        self.assertContains(response, "GRN Register")
        self.assertNotContains(response, "no provision budget committed yet")

    def test_no_task_id_does_not_fallback_to_first_task(self):
        ProjectTask.objects.create(project_id="133", description="First task")
        ProjectTask.objects.create(project_id="999", description="Second task")
        url = reverse("gm_aie_disbursement")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Select a project task")

    def test_funds_available_after_ceo_release(self):
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
