"""GM ↔ CEO budget review workflow tests."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.budget_review import ceo_can_approve_budget, gm_can_submit_budget
from accounts.models import BudgetReviewEvent, ProjectBudget, ProjectTask, UserCategory
from accounts.roles import CEO, GENERAL_MANAGER


class BudgetReviewWorkflowTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.ceo_cat = UserCategory.objects.create(code=CEO, description="CEO", rank=80)
        self.gm_cat = UserCategory.objects.create(code=GENERAL_MANAGER, description="GM", rank=50)
        self.gm = User.objects.create_user(username="gm_review", password="test-pass-123")
        self.ceo = User.objects.create_user(username="ceo_review", password="test-pass-123")
        from accounts.models import UserAccount

        UserAccount.objects.create(
            user=self.gm, staff_no="GMR01", first_name="G", last_name="M",
            designation="GM", contact_address="HQ", phone="0", email="gm@test.local",
            access_level=self.gm_cat,
        )
        UserAccount.objects.create(
            user=self.ceo, staff_no="CEOR01", first_name="C", last_name="E",
            designation="CEO", contact_address="HQ", phone="0", email="ceo@test.local",
            access_level=self.ceo_cat,
        )
        self.task = ProjectTask.objects.create(project_id="REV-1", description="Review workflow task")
        self.budget = ProjectBudget.objects.create(
            task=self.task,
            budget_type=ProjectBudget.BUDGET_ADHOC_MISC,
            budget_label="Ad-hoc",
            total_authorized_budget=Decimal("3000.00"),
            review_status=ProjectBudget.REVIEW_PROVISION,
        )

    def test_ceo_cannot_approve_before_gm_submits(self):
        self.assertFalse(ceo_can_approve_budget(self.budget))
        self.budget.review_status = ProjectBudget.REVIEW_WITH_CEO
        self.budget.save(update_fields=["review_status"])
        self.assertTrue(ceo_can_approve_budget(self.budget))

    def test_ceo_return_and_resubmit_flow(self):
        self.budget.review_status = ProjectBudget.REVIEW_WITH_CEO
        self.budget.save(update_fields=["review_status"])
        self.client.login(username="ceo_review", password="test-pass-123")
        response = self.client.post(
            reverse("budget_approval") + f"?task_id={self.task.project_id}",
            {"return_to_gm": "1", "return_reason": "Labour line too high — revise."},
        )
        self.assertEqual(response.status_code, 302)
        self.budget.refresh_from_db()
        self.assertEqual(self.budget.review_status, ProjectBudget.REVIEW_RETURNED)
        self.assertTrue(gm_can_submit_budget(self.budget))
        self.assertEqual(
            BudgetReviewEvent.objects.filter(action=BudgetReviewEvent.ACTION_CEO_RETURN).count(),
            1,
        )
