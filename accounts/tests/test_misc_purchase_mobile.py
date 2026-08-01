"""Regression tests for misc-purchase mobile task selection."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import (
    BOMHeader,
    BOMItem,
    GLAccount,
    MiscPurchaseItem,
    ProjectTask,
)
from accounts.views import _misc_channel_allowed, _misc_purchase_task_list, _print_items_count


class MiscPurchaseMobileTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_superuser(
            username="mobile_test_admin",
            email="mobile@test.local",
            password="test-pass-123",
        )
        self.client = Client()
        self.client.login(username="mobile_test_admin", password="test-pass-123")
        self.task = ProjectTask.objects.create(
            project_id="TOMOG-PIONEER-HWF-00026",
            description="Pioneer HWF misc requisition task",
        )
        GLAccount.objects.create(
            gl_account_id="6000",
            debit_credit="DR",
            description="Misc expense",
            currency="KES",
            amount=Decimal("0"),
        )

    def test_misc_channel_allowed_for_fresh_task(self):
        allowed, _reason = _misc_channel_allowed(self.task)
        self.assertTrue(allowed)

    def test_task_list_includes_active_task(self):
        tasks = _misc_purchase_task_list(self.task)
        self.assertTrue(tasks.filter(project_id=self.task.project_id).exists())

    def test_workspace_picker_renders_for_task_url(self):
        url = reverse("misc_purchase_builder")
        response = self.client.get(url, {"task_id": self.task.project_id})
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("misc-workspace-task-bar", html)
        self.assertIn('id="miscTaskSelect-workspace"', html)
        self.assertIn(self.task.project_id, html)
        self.assertIn("Pioneer HWF misc", html)

    def test_workspace_picker_selected_option(self):
        url = reverse("misc_purchase_builder")
        response = self.client.get(url, {"task_id": self.task.project_id})
        html = response.content.decode()
        needle = f'value="{self.task.project_id}"'
        idx = html.find(needle)
        self.assertGreater(idx, -1, "Task option missing from picker")
        snippet = html[idx : idx + 120]
        self.assertIn("selected", snippet)

    def test_sidebar_picker_still_present_for_desktop(self):
        url = reverse("misc_purchase_builder")
        response = self.client.get(url, {"task_id": self.task.project_id})
        html = response.content.decode()
        self.assertIn('id="miscTaskSelect-sidebar"', html)

    def test_free_form_add_still_works_without_bom(self):
        url = reverse("misc_purchase_builder") + f"?task_id={self.task.project_id}"
        self.client.post(url, {"new_ro": "1", "task_id": self.task.project_id})
        response = self.client.post(
            url,
            {
                "add_misc_purchase": "1",
                "task_id": self.task.project_id,
                "description": "Ad-hoc cable",
                "uom": "m",
                "qty": "10",
                "unit_price": "25.50",
            },
        )
        self.assertEqual(response.status_code, 302)
        item = MiscPurchaseItem.objects.get(task=self.task, description="Ad-hoc cable")
        self.assertIsNone(item.source_bom_item_id)
        self.assertEqual(item.unit_price, Decimal("25.50"))

    def test_bom_backed_task_adds_from_main_bom_with_known_price(self):
        bom = BOMHeader.objects.create(task=self.task, status=BOMHeader.STATUS_DRAFT)
        line = BOMItem.objects.create(
            header=bom,
            pillar_id=2,
            description="Isiolo feeder cable",
            qty=Decimal("12"),
            uom="m",
            unit_price=Decimal("100"),
            source_package_code="EL-01",
            source_bill_ref="E1",
            source_line_key="tender-line:test-1",
        )
        BOMItem.objects.create(
            header=bom,
            pillar_id=2,
            description="Civil blinding",
            qty=Decimal("5"),
            uom="m3",
            unit_price=Decimal("50"),
            source_package_code="CV-01",
            source_bill_ref="C1",
            source_line_key="tender-line:test-2",
        )
        url = reverse("misc_purchase_builder") + f"?task_id={self.task.project_id}"
        self.client.post(url, {"new_ro": "1", "task_id": self.task.project_id})
        page = self.client.get(url)
        self.assertContains(page, "Load main BOM item categories")
        self.assertContains(page, "EL-01")
        self.assertContains(page, "CV-01")
        self.assertNotContains(page, 'placeholder="Item description"')

        # Free-text create is rejected once a main BOM exists.
        blocked = self.client.post(
            url,
            {
                "add_misc_purchase": "1",
                "task_id": self.task.project_id,
                "description": "Should not create",
                "uom": "EA",
                "qty": "1",
                "unit_price": "9",
            },
            follow=True,
        )
        self.assertContains(blocked, "Select a BOM category")
        self.assertFalse(
            MiscPurchaseItem.objects.filter(description="Should not create").exists()
        )

        loaded = self.client.post(
            url,
            {
                "load_misc_bom_categories": "1",
                "task_id": self.task.project_id,
                "package_codes": ["EL-01"],
            },
            follow=True,
        )
        self.assertContains(loaded, "Isiolo feeder cable")
        self.assertContains(loaded, "Item / specification")
        self.assertContains(loaded, "Standard unit price")
        self.assertContains(loaded, 'name="qty_%s"' % line.pk)
        self.assertNotContains(loaded, "Civil blinding")

        added = self.client.post(
            url,
            {
                "add_misc_bom_priced_lines": "1",
                "task_id": self.task.project_id,
                "bom_item_id": str(line.pk),
                f"qty_{line.pk}": "12.5",
                f"unit_price_{line.pk}": "87.25",
            },
        )
        self.assertEqual(added.status_code, 302)
        item = MiscPurchaseItem.objects.get(task=self.task, source_bom_item=line)
        self.assertEqual(item.description, "Isiolo feeder cable")
        self.assertEqual(item.uom, "m")
        self.assertEqual(item.qty, Decimal("12.50"))
        self.assertEqual(item.unit_price, Decimal("87.25"))
        self.assertEqual(item.total, Decimal("1090.62"))
        self.assertFalse(
            MiscPurchaseItem.objects.filter(description="Civil blinding").exists()
        )


class PrintGuardHelperTests(TestCase):
    def test_print_items_count_empty_list(self):
        self.assertEqual(_print_items_count([]), 0)

    def test_print_items_count_list(self):
        self.assertEqual(_print_items_count([1, 2, 3]), 3)

    def test_print_items_count_queryset(self):
        ProjectTask.objects.create(project_id="QTASK-001", description="Queryset task")
        self.assertEqual(_print_items_count(ProjectTask.objects.filter(project_id="QTASK-001")), 1)
        self.assertEqual(_print_items_count(ProjectTask.objects.none()), 0)
