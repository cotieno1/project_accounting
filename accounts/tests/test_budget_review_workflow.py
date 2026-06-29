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

    def test_ceo_can_approve_adhoc_provision_without_gm_memo(self):
        self.assertTrue(ceo_can_approve_budget(self.budget))

    def test_budget_approval_page_enables_approve_for_adhoc_provision(self):
        self.client.login(username="ceo_review", password="test-pass-123")
        response = self.client.get(
            reverse("budget_approval") + f"?task_id={self.task.project_id}"
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["can_approve"])
        self.assertNotContains(
            response,
            'name="approve_budget" class="btn-action btn-success" style="width:100%;" disabled',
        )

    def test_ceo_cannot_approve_returned_until_gm_resubmits(self):
        self.budget.review_status = ProjectBudget.REVIEW_RETURNED
        self.budget.save(update_fields=["review_status"])
        self.assertFalse(ceo_can_approve_budget(self.budget))

    def test_ceo_can_approve_after_gm_submits_memo(self):
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

    def test_ceo_desk_syncs_adhoc_budget_from_mro_without_project_budget(self):
        from accounts.models import MiscPurchaseOrder, MiscRequisitionOrder

        task = ProjectTask.objects.create(project_id="MRO-ONLY", description="MRO only task")
        mpo = MiscPurchaseOrder.objects.create(
            task=task,
            funding_status="LOCKED",
            mpo_number="MPO-MRO-1",
            total_amount=Decimal("2500.00"),
        )
        MiscRequisitionOrder.objects.create(
            task=task,
            source_mpo=mpo,
            mro_number="MRO-2026-001",
            funding_status="LOCKED",
            total_amount=Decimal("2500.00"),
        )
        self.assertFalse(ProjectBudget.objects.filter(task=task).exists())
        self.client.login(username="ceo_review", password="test-pass-123")
        response = self.client.get(reverse("budget_approval") + f"?task_id={task.project_id}")
        self.assertEqual(response.status_code, 200)
        budget = ProjectBudget.objects.get(task=task)
        self.assertEqual(budget.budget_type, ProjectBudget.BUDGET_ADHOC_MISC)
        self.assertEqual(budget.material_total_cost, Decimal("2500.00"))
        self.assertTrue(response.context["budget_summary"]["has_budget"])
        self.assertTrue(response.context["can_approve"])
        self.assertNotContains(response, "Complete Bid Evaluation")

    def test_adhoc_fund_release_uses_dedicated_print_template(self):
        from accounts.models import CEOFundRelease
        from django.urls import reverse

        self.budget.is_ceo_approved = True
        self.budget.save(update_fields=["is_ceo_approved"])
        release = CEOFundRelease.objects.create(
            release_number="PV-DSB-2026-0099",
            task=self.task,
            budget=self.budget,
            amount=Decimal("3000.00"),
            bank_reference="BNK-ADHOC-001",
            authorized_by=self.ceo,
        )
        self.client.login(username="ceo_review", password="test-pass-123")
        response = self.client.get(
            reverse("print_ceo_fund_release_voucher", kwargs={"release_id": release.id})
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "ceo_adhoc_misc_fund_release_print.html")
        self.assertContains(response, "Ad-Hoc Misc Budget")
        self.assertContains(response, "no LPO or supplier procurement")
