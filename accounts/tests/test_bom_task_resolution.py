"""Regression tests for BOM builder task_id resolution and mobile workspace picker."""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import BOMHeader, ProjectTask
from accounts.views import _normalize_task_id, _task_from_request


class NormalizeTaskIdTests(TestCase):
    def test_plain_id(self):
        self.assertEqual(_normalize_task_id("133"), "133")

    def test_quoted_list_string(self):
        self.assertEqual(_normalize_task_id("['133']"), "133")

    def test_bracketed_without_quotes(self):
        self.assertEqual(_normalize_task_id("[133]"), "133")

    def test_double_quoted(self):
        self.assertEqual(_normalize_task_id('"TOMOG-001"'), "TOMOG-001")

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
        response = self.client.get(url, {"task_id": "['BOM-TASK-133']"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "BOM-TASK-133")
        self.assertContains(response, "Start BOM")

    def test_unknown_explicit_task_shows_error_not_wrong_task(self):
        ProjectTask.objects.create(
            project_id="OTHER-TASK-999",
            description="Different task",
        )
        url = reverse("bom_builder")
        response = self.client.get(url, {"task_id": "['NO-SUCH-TASK']"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "was not found")

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

    def test_task_from_request_no_fallback_on_bad_explicit_id(self):
        from django.test import RequestFactory

        ProjectTask.objects.create(project_id="FALLBACK-001", description="First")
        factory = RequestFactory()
        request = factory.get("/bom-builder/", {"task_id": "['MISSING']"})
        request.session = {}
        task = _task_from_request(request, ProjectTask.objects.all())
        self.assertIsNone(task)


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
