"""GM desk hold when ad-hoc disbursements precede CEO budget approval."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import (
    AdHocOfficerPaymentVoucher,
    MiscPurchaseOrder,
    ProjectBudget,
    ProjectTask,
)
from accounts.views import _gm_budget_compliance_hold


class GmBudgetComplianceHoldTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_superuser(
            username="gm_hold_admin",
            email="gmhold@test.local",
            password="test-pass-123",
        )
        self.client = Client()
        self.client.login(username="gm_hold_admin", password="test-pass-123")
        self.task = ProjectTask.objects.create(project_id="1", description="Forensic task")
        self.budget = ProjectBudget.objects.create(
            task=self.task,
            budget_type=ProjectBudget.BUDGET_ADHOC_MISC,
            budget_label="Ad-hoc Task 1",
            material_total_cost=Decimal("5000.00"),
            total_authorized_budget=Decimal("6000.00"),
            review_status=ProjectBudget.REVIEW_PROVISION,
        )
        self.mpo = MiscPurchaseOrder.objects.create(
            task=self.task,
            funding_status="SUBMITTED",
            is_sourcing=False,
            mpo_number="MPO-TASK-1",
            total_amount=Decimal("5000.00"),
        )

    def test_hold_detects_officer_pv_without_ceo_approval(self):
        AdHocOfficerPaymentVoucher.objects.create(
            mpo=self.mpo,
            task=self.task,
            officer_name="Officer A",
            amount=Decimal("1200.00"),
            payment_method="CASH",
        )
        hold = _gm_budget_compliance_hold(self.task)
        self.assertIsNotNone(hold)
        self.assertEqual(hold["officer_pv_count"], 1)
        self.assertEqual(hold["disbursed_total"], Decimal("1200.00"))

    def test_hold_cleared_after_ceo_approval(self):
        AdHocOfficerPaymentVoucher.objects.create(
            mpo=self.mpo,
            task=self.task,
            officer_name="Officer A",
            amount=Decimal("500.00"),
            payment_method="CASH",
        )
        self.budget.is_ceo_approved = True
        self.budget.save(update_fields=["is_ceo_approved"])
        self.assertIsNone(_gm_budget_compliance_hold(self.task))

    def test_gm_desk_grays_out_and_shows_reminder_form(self):
        AdHocOfficerPaymentVoucher.objects.create(
            mpo=self.mpo,
            task=self.task,
            officer_name="Officer A",
            amount=Decimal("800.00"),
            payment_method="CASH",
        )
        url = reverse("gm_aie_disbursement")
        response = self.client.get(url, {"task_id": "1"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "gm-desk--hold")
        self.assertContains(response, "Task on hold")
        self.assertContains(response, "Send reminder to CEO")
        self.assertContains(response, "gm-workspace-tools is-blocked")

    def test_reminder_post_blocked_while_on_hold_for_other_actions(self):
        AdHocOfficerPaymentVoucher.objects.create(
            mpo=self.mpo,
            task=self.task,
            officer_name="Officer A",
            amount=Decimal("300.00"),
            payment_method="CASH",
        )
        url = reverse("gm_aie_disbursement")
        response = self.client.post(
            url,
            {
                "task_id": "1",
                "post_payment": "1",
                "budget_line": "MATERIAL",
                "amount": "100",
                "description": "Should block",
            },
        )
        self.assertEqual(response.status_code, 302)
        follow = self.client.get(url, {"task_id": "1"})
        self.assertContains(follow, "Task on hold")

    def test_send_ceo_reminder_logs_event(self):
        from accounts.models import BudgetReviewEvent

        AdHocOfficerPaymentVoucher.objects.create(
            mpo=self.mpo,
            task=self.task,
            officer_name="Officer A",
            amount=Decimal("900.00"),
            payment_method="CASH",
        )
        url = reverse("gm_aie_disbursement")
        response = self.client.post(
            url,
            {
                "task_id": "1",
                "action": "send_ceo_budget_reminder",
                "reminder_notes": "Please approve Task 1 MRO baseline.",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            BudgetReviewEvent.objects.filter(
                action=BudgetReviewEvent.ACTION_GM_REMIND,
                task=self.task,
            ).exists()
        )
        self.budget.refresh_from_db()
        self.assertEqual(self.budget.review_status, ProjectBudget.REVIEW_WITH_CEO)
