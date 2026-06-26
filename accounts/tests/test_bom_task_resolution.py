"""Regression tests for BOM builder task_id resolution and mobile workspace picker."""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import BOMHeader, ProjectTask
from accounts.views import (
    _bom_active_task,
    _bom_can_start_bom,
    _normalize_task_id,
    _resolve_project_task,
    _task_from_request,
)


class NormalizeTaskIdTests(TestCase):
    def test_plain_id(self):
        self.assertEqual(_normalize_task_id("133"), "133")

    def test_quoted_list_string(self):
        self.assertEqual(_normalize_task_id("['133']"), "133")

    def test_bracketed_without_quotes(self):
        self.assertEqual(_normalize_task_id("[133]"), "133")

    def test_double_quoted(self):
        self.assertEqual(_normalize_task_id('"TOMOG-001"'), "TOMOG-001")

    def test_normalize_task_description_strips_brackets(self):
        from accounts.views import _normalize_task_description

        self.assertEqual(_normalize_task_description("['Building Flats ']"), "Building Flats")
        self.assertEqual(_normalize_task_description("['build x house']"), "build x house")

    def test_empty_and_none(self):
        self.assertEqual(_normalize_task_id(None), "")
        self.assertEqual(_normalize_task_id(""), "")
        self.assertEqual(_normalize_task_id("   "), "")


class BomBuilderTaskResolutionTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_superuser(
            username="bom_task_admin",
            email="bom@test.local",
            password="test-pass-123",
        )
        self.client = Client()
        self.client.login(username="bom_task_admin", password="test-pass-123")
        self.task = ProjectTask.objects.create(
            project_id="BOM-TASK-133",
            description="Fresh major task for BOM",
        )

    def test_malformed_url_resolves_to_task(self):
        url = reverse("bom_builder")
        response = self.client.get(url, {"task_id": "['BOM-TASK-133']"}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "BOM-TASK-133")
        self.assertContains(response, "Start BOM")

    def test_bad_url_falls_back_to_existing_task(self):
        ProjectTask.objects.create(
            project_id="OTHER-TASK-999",
            description="Different task",
        )
        url = reverse("bom_builder")
        response = self.client.get(url, {"task_id": "NO-SUCH-TASK"})
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "was not found")
        self.assertContains(response, self.task.project_id)

    def test_placeholder_task_id_falls_back_without_error(self):
        url = reverse("bom_builder")
        response = self.client.get(url, {"task_id": "YOUR-ACTUAL-TASK-ID"})
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "was not found")
        self.assertContains(response, self.task.project_id)

    def test_workspace_picker_visible_on_mobile_markup(self):
        url = reverse("bom_builder")
        response = self.client.get(url, {"task_id": self.task.project_id})
        html = response.content.decode()
        self.assertIn("bom-workspace-task-bar", html)
        self.assertIn('id="bomWorkspaceTaskSelect"', html)
        self.assertIn(self.task.project_id, html)

    def test_start_bom_post_creates_header(self):
        url = reverse("bom_builder") + f"?task_id={self.task.project_id}"
        response = self.client.post(
            url,
            {"new_bom": "1", "task_id": self.task.project_id},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(BOMHeader.objects.filter(task=self.task).exists())

    def test_start_bom_shows_line_entry_form(self):
        url = reverse("bom_builder") + f"?task_id={self.task.project_id}"
        self.client.post(url, {"new_bom": "1", "task_id": self.task.project_id})
        response = self.client.get(url)
        html = response.content.decode()
        self.assertIn("Add your first line below", html)
        self.assertIn('name="add_item"', html)
        self.assertNotContains(response, 'name="new_bom"')

    def test_task_from_request_no_fallback_on_bad_explicit_id(self):
        from django.test import RequestFactory

        ProjectTask.objects.create(project_id="FALLBACK-001", description="First")
        factory = RequestFactory()
        request = factory.get("/bom-builder/", {"task_id": "['MISSING']"})
        request.session = {}
        task = _task_from_request(request, ProjectTask.objects.all())
        self.assertIsNone(task)

    def test_bom_active_task_ignores_bad_url(self):
        from django.test import RequestFactory

        factory = RequestFactory()
        request = factory.get("/bom-builder/", {"task_id": "BAD-ID"})
        request.session = {"active_task_id": self.task.project_id}
        request.method = "GET"
        task = _bom_active_task(request)
        self.assertEqual(task.project_id, self.task.project_id)

    def test_legacy_bracket_pk_task_133_selectable(self):
        ProjectTask.objects.create(
            project_id="['133']",
            description="New task 133",
        )
        url = reverse("bom_builder")
        response = self.client.get(url, {"task_id": "133"}, follow=True)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn(">133<", html)
        self.assertNotIn("['133']", html)
        self.assertContains(response, "Start BOM")

    def test_malformed_tomog_url_selects_task(self):
        ProjectTask.objects.create(
            project_id="TOMOG-PIONEER-HWF-000029",
            description="Pioneer HWF task 29",
        )
        url = reverse("bom_builder")
        response = self.client.get(url, {"task_id": "['TOMOG-PIONEER-HWF-000029']"}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "TOMOG-PIONEER-HWF-000029")
        self.assertContains(response, "Start BOM")

    def test_can_start_bom_only_checks_misc_and_bom(self):
        task = ProjectTask.objects.create(project_id="133", description="Clean id")
        self.assertTrue(_bom_can_start_bom(task))
        BOMHeader.objects.create(task=task, status=BOMHeader.STATUS_DRAFT)
        self.assertFalse(_bom_can_start_bom(task))


class BudgetApprovalTaskIdTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_superuser(
            username="budget_approval_admin",
            email="budget@test.local",
            password="test-pass-123",
        )
        self.client = Client()
        self.client.login(username="budget_approval_admin", password="test-pass-123")

    def test_malformed_bracket_url_redirects_clean(self):
        ProjectTask.objects.create(
            project_id="['1233_0900']",
            description="Bracket legacy task",
        )
        url = reverse("budget_approval")
        response = self.client.get(url, {"task_id": "['1233_0900']"}, follow=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn("task_id=1233_0900", response.url)
        self.assertNotIn("%27", response.url)

    def test_clean_url_renders_without_brackets(self):
        ProjectTask.objects.create(
            project_id="['1233_0900']",
            description="Bracket legacy task",
        )
        url = reverse("budget_approval")
        response = self.client.get(url, {"task_id": "1233_0900"}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "1233_0900")
        self.assertNotContains(response, "['1233_0900']")


class UnifiedApiCreateTaskTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_superuser(
            username="api_task_admin",
            email="api@test.local",
            password="test-pass-123",
        )
        self.client = Client()
        self.client.login(username="api_task_admin", password="test-pass-123")

    def test_create_task_returns_clean_bom_builder_url(self):
        url = reverse("api_create", kwargs={"entity_type": "task"})
        response = self.client.post(
            url,
            {
                "mode": "create",
                "project_id": "NEW-TASK-777",
                "description": "Created from dashboard",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "success")
        self.assertIn("bom_builder_url", data)
        self.assertIn("task_id=NEW-TASK-777", data["bom_builder_url"])
        self.assertNotIn("%27", data["bom_builder_url"])
