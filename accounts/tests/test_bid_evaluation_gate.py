"""Bid evaluation access gate - BOM, RO, RFQ required; closed after LPO."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import (
    BOMHeader,
    BOMTransaction,
    LPOTransaction,
    Product,
    ProjectBuildCategory,
    ProjectTask,
    RequisitionOrder,
    RequisitionOrderItem,
    RFQTransaction,
    SupplierAccount,
)
from accounts.views import _bid_evaluation_gate, _bid_evaluation_workspace


class BidEvaluationGateHelperTests(TestCase):
    def setUp(self):
        self.task = ProjectTask.objects.create(
            project_id="BID-GATE-TASK",
            description="Major procurement task",
        )
        self.cat = ProjectBuildCategory.objects.create(
            build_cat_id="CAT-BID",
            description="Civil",
        )
        self.product = Product.objects.create(
            product_id="PROD-BID",
            description="Cement",
            unit_of_measure="bag",
        )
        self.supplier = SupplierAccount.objects.create(
            supplier_id="SUP-BID",
            description="Acme Supplies",
            bank_account_number="123",
            contact_address="Nairobi",
            phone="0700000000",
            email="acme@example.com",
        )

    def _seed_bom_ro_rfq(self):
        bom = BOMHeader.objects.create(
            task=self.task,
            status=BOMHeader.STATUS_SENT_TO_GM,
        )
        ro = RequisitionOrder.objects.create(
            ro_no="RO-BID-001",
            task=self.task,
        )
        RequisitionOrderItem.objects.create(
            ro=ro,
            quantity=Decimal("10"),
            uom="bag",
            tech_spec_summary="Portland cement",
        )
        bt = BOMTransaction.objects.create(
            project_task=self.task,
            build_category=self.cat,
            product=self.product,
            quantity_required=Decimal("10"),
        )
        RFQTransaction.objects.create(
            rfq_no="RFQ-BID-001",
            bom_item=bt,
            supplier=self.supplier,
        )
        return bom, ro

    def test_blocks_without_bom_ro_rfq(self):
        allowed, message, snap = _bid_evaluation_gate(self.task)
        self.assertFalse(allowed)
        self.assertIn("not reached", message.lower())

    def test_workspace_uncommitted_stage(self):
        ws = _bid_evaluation_workspace(self.task)
        self.assertEqual(ws["stage"], "uncommitted")
        self.assertFalse(ws["allowed"])
        self.assertFalse(ws["show_prerequisites"])

    def test_allows_when_prerequisites_met(self):
        self._seed_bom_ro_rfq()
        allowed, message, _ = _bid_evaluation_gate(self.task)
        self.assertTrue(allowed)
        self.assertEqual(message, "")
        ws = _bid_evaluation_workspace(self.task)
        self.assertEqual(ws["stage"], "open")

    def test_blocks_when_lpo_issued(self):
        self._seed_bom_ro_rfq()
        LPOTransaction.objects.create(project_task=self.task)
        allowed, message, snap = _bid_evaluation_gate(self.task)
        self.assertFalse(allowed)
        self.assertIn("LPO", message)
        ws = _bid_evaluation_workspace(self.task)
        self.assertEqual(ws["stage"], "completed")


class BidEvaluationGateViewTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_superuser(
            username="bid_gate_admin",
            email="bidgate@test.local",
            password="test-pass-123",
        )
        self.client = Client()
        self.client.login(username="bid_gate_admin", password="test-pass-123")
        self.task = ProjectTask.objects.create(
            project_id="1233_0900",
            description="Uncommitted task",
        )
        self.url = reverse("bid_evaluation_terminal")

    def test_uncommitted_task_shows_lane_choice(self):
        response = self.client.get(self.url, {"task_id": self.task.project_id})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "no mans land")
        self.assertContains(response, "Create BOM")
        self.assertContains(response, "Create Misc Purchase")
        self.assertContains(response, "bid-eval-lane-choice")
        self.assertContains(response, "Abandon (Esc)")
        self.assertNotContains(response, "Select Two Bidders")
        self.assertNotContains(response, "Procurement prerequisites")

    def test_malformed_bracket_url_redirects_clean(self):
        ProjectTask.objects.create(
            project_id="['1233_0900']",
            description="Bracket legacy task",
        )
        response = self.client.get(self.url, {"task_id": "['1233_0900']"}, follow=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn("task_id=1233_0900", response.url)

    def test_post_award_rejected_without_prerequisites(self):
        response = self.client.post(
            self.url,
            {
                "task_id": self.task.project_id,
                "supplier_ids_csv": "S1,S2",
                "awarded_supplier_id": "S1",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Create BOM")
