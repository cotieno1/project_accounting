"""RO draft confirm workflow tests."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import ProjectTask, RequisitionOrder, RequisitionOrderItem, UserAccount


class ROConfirmWorkflowTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="ro_officer", password="test-pass-123")
        UserAccount.objects.create(
            user=self.user,
            staff_no="RO01",
            first_name="R",
            last_name="O",
            designation="Engineer",
            contact_address="HQ",
            phone="0",
            email="ro@test.local",
        )
        self.task = ProjectTask.objects.create(
            project_id="RO-WF-1",
            description="Workflow test task",
        )
        self.client = Client()
        self.client.login(username="ro_officer", password="test-pass-123")

    def _draft_with_item(self):
        ro = RequisitionOrder.objects.create(task=self.task, status="DRAFT")
        RequisitionOrderItem.objects.create(
            ro=ro,
            quantity=Decimal("5"),
            uom="bag",
            tech_spec_summary="Cement",
        )
        return ro

    def test_new_ro_has_no_number_until_confirm(self):
        ro = self._draft_with_item()
        self.assertIsNone(ro.ro_no)
        self.assertTrue(ro.is_editable)

    def test_confirm_assigns_ro_number_and_locks(self):
        ro = self._draft_with_item()
        response = self.client.post(reverse("confirm_ro", args=[ro.id]))
        self.assertEqual(response.status_code, 302)
        ro.refresh_from_db()
        self.assertTrue(ro.ro_no)
        self.assertEqual(ro.status, "CONFIRMED")
        self.assertIsNotNone(ro.confirmed_at)
        self.assertFalse(ro.is_editable)

    def test_confirm_is_one_time_only(self):
        ro = self._draft_with_item()
        self.client.post(reverse("confirm_ro", args=[ro.id]))
        ro.refresh_from_db()
        first_no = ro.ro_no
        response = self.client.post(reverse("confirm_ro", args=[ro.id]))
        self.assertEqual(response.status_code, 302)
        ro.refresh_from_db()
        self.assertEqual(ro.ro_no, first_no)

    def test_draft_print_blocked_after_confirm(self):
        ro = self._draft_with_item()
        self.client.post(reverse("confirm_ro", args=[ro.id]))
        response = self.client.get(reverse("print_ro_draft_view", args=[ro.id]))
        self.assertEqual(response.status_code, 302)

    def test_final_print_requires_confirm(self):
        ro = self._draft_with_item()
        response = self.client.get(reverse("print_ro_view", args=[ro.id]))
        self.assertEqual(response.status_code, 302)

    def test_final_print_after_confirm(self):
        ro = self._draft_with_item()
        self.client.post(reverse("confirm_ro", args=[ro.id]))
        ro.refresh_from_db()
        response = self.client.get(reverse("print_ro_view", args=[ro.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, ro.ro_no)

    def test_update_item_blocked_after_confirm(self):
        ro = self._draft_with_item()
        item = ro.items.first()
        self.client.post(reverse("confirm_ro", args=[ro.id]))
        self.client.post(
            reverse("ro_builder") + f"?task_id={self.task.project_id}",
            {"update_item": "1", "item_id": item.id, "description": "Changed", "uom": "bag", "qty": "5"},
        )
        item.refresh_from_db()
        self.assertEqual(item.tech_spec_summary, "Cement")

    def test_delete_item_blocked_after_confirm(self):
        ro = self._draft_with_item()
        item = ro.items.first()
        self.client.post(reverse("confirm_ro", args=[ro.id]))
        self.client.post(
            reverse("ro_builder") + f"?task_id={self.task.project_id}",
            {"delete_item": "1", "item_id": item.id},
        )
        self.assertTrue(RequisitionOrderItem.objects.filter(id=item.id).exists())