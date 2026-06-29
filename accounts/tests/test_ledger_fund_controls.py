"""GL fund-control tests — GM cannot pay without CEO-released wallet balance."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from accounts.ledger import (
    assert_task_can_disburse,
    backfill_ceo_fund_release_postings,
    build_fund_ledger_report,
    ensure_fund_control_accounts,
    fund_ceo_disbursement_account,
    gm_operating_gl_balance,
    post_ceo_fund_release,
    post_officer_advance_voucher,
    sync_fund_control_gl_balances,
    task_gm_wallet_balance,
)
from accounts.models import (
    AdHocOfficerPaymentVoucher,
    CEOFundRelease,
    MiscPurchaseOrder,
    ProjectBudget,
    ProjectTask,
)


class LedgerFundControlTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_superuser(
            username="ledger_admin",
            email="ledger@test.local",
            password="test-pass-123",
        )
        self.task = ProjectTask.objects.create(project_id="LEDGER-1", description="Ledger test task")
        self.budget = ProjectBudget.objects.create(
            task=self.task,
            budget_type=ProjectBudget.BUDGET_ADHOC_MISC,
            budget_label="Ad-hoc provision",
            version=1,
            is_ceo_approved=True,
            total_authorized_budget=Decimal("5000.00"),
        )
        ensure_fund_control_accounts()
        fund_ceo_disbursement_account(Decimal("10000.00"), self.user)
        self.release = CEOFundRelease.objects.create(
            release_number="PV-DSB-TEST-001",
            task=self.task,
            budget=self.budget,
            amount=Decimal("5000.00"),
            authorized_by=self.user,
        )
        post_ceo_fund_release(self.release, self.user)

    def test_wallet_balance_after_release(self):
        self.assertEqual(task_gm_wallet_balance(self.task), Decimal("5000.00"))
        self.assertEqual(gm_operating_gl_balance(), Decimal("5000.00"))

    def test_cannot_disburse_without_wallet(self):
        broke_task = ProjectTask.objects.create(project_id="BROKE-1", description="No funds")
        with self.assertRaises(ValueError):
            assert_task_can_disburse(broke_task, Decimal("100.00"))

    def test_officer_voucher_posts_to_employee_and_gm_control(self):
        mpo = MiscPurchaseOrder.objects.create(
            task=self.task,
            mpo_number="RO-LEDGER-001",
            funding_status="SUBMITTED",
        )
        voucher = AdHocOfficerPaymentVoucher.objects.create(
            mpo=mpo,
            task=self.task,
            officer_name="Test Officer",
            payment_method="CASH",
            amount=Decimal("1500.00"),
            created_by=self.user,
        )
        post_officer_advance_voucher(voucher, self.user)
        voucher.refresh_from_db()
        self.assertIsNotNone(voucher.ledger_posting_id)
        self.assertEqual(task_gm_wallet_balance(self.task), Decimal("3500.00"))
        self.assertEqual(gm_operating_gl_balance(), Decimal("3500.00"))

    def test_officer_voucher_blocked_when_exceeds_wallet(self):
        mpo = MiscPurchaseOrder.objects.create(
            task=self.task,
            mpo_number="RO-LEDGER-002",
            funding_status="SUBMITTED",
        )
        voucher = AdHocOfficerPaymentVoucher.objects.create(
            mpo=mpo,
            task=self.task,
            officer_name="Test Officer",
            payment_method="CASH",
            amount=Decimal("6000.00"),
            created_by=self.user,
        )
        with self.assertRaises(ValueError):
            post_officer_advance_voucher(voucher, self.user)

    def test_ledger_report_includes_cost_center_on_gl_lines(self):
        report = build_fund_ledger_report(task=self.task)
        self.assertTrue(report["posting_rows"])
        for row in report["posting_rows"]:
            self.assertEqual(row["cost_center_id"], "LEDGER-1")
            self.assertIn("Ledger test", row["cost_center_label"])

    def test_backfill_posts_release_when_ledger_missing(self):
        release = CEOFundRelease.objects.create(
            release_number="PV-DSB-BACKFILL-001",
            task=self.task,
            budget=self.budget,
            amount=Decimal("2000.00"),
            authorized_by=self.user,
        )
        self.assertIsNone(release.ledger_posting_id)
        posted = backfill_ceo_fund_release_postings(self.user)
        self.assertEqual(posted, 1)
        release.refresh_from_db()
        self.assertIsNotNone(release.ledger_posting_id)
        report = build_fund_ledger_report(task=self.task, backfill=False)
        self.assertEqual(report["gm_gl"].amount, Decimal("7000.00"))
        self.assertEqual(task_gm_wallet_balance(self.task), Decimal("7000.00"))

    def test_sync_gl_balances_from_journal(self):
        sync_fund_control_gl_balances()
        self.assertEqual(gm_operating_gl_balance(), Decimal("5000.00"))
