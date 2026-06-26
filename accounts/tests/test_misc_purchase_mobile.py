"""Regression tests for misc-purchase mobile task selection."""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import ProjectTask
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

    def test_legacy_bracket_task_id_selectable(self):
        ProjectTask.objects.create(
            project_id="['100']",
            description="Misc task 100",
        )
        url = reverse("misc_purchase_builder")
        response = self.client.get(url, {"task_id": "100"}, follow=True)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn(">100<", html)
        self.assertNotIn("['100']", html)
        self.assertIn('value="100"', html)

    def test_malformed_bracket_url_redirects_clean(self):
        ProjectTask.objects.create(
            project_id="['1233_0900']",
            description="Underscore misc task",
        )
        url = reverse("misc_purchase_builder")
        response = self.client.get(url, {"task_id": "['1233_0900']"}, follow=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn("task_id=1233_0900", response.url)


class PrintGuardHelperTests(TestCase):
    def test_print_items_count_empty_list(self):
        self.assertEqual(_print_items_count([]), 0)

    def test_print_items_count_list(self):
        self.assertEqual(_print_items_count([1, 2, 3]), 3)

    def test_print_items_count_queryset(self):
        ProjectTask.objects.create(project_id="QTASK-001", description="Queryset task")
        self.assertEqual(_print_items_count(ProjectTask.objects.filter(project_id="QTASK-001")), 1)
        self.assertEqual(_print_items_count(ProjectTask.objects.none()), 0)
