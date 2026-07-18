"""Tests for identifier normalization and task id cleanup."""

from django.test import TestCase

from accounts.identifiers import clean_all_task_ids, identifier_needs_cleaning, normalize_identifier
from accounts.models import ProjectTask


class NormalizeIdentifierTests(TestCase):
    def test_testing_bom_with_spaces(self):
        self.assertEqual(normalize_identifier("['Testing BOM ']"), "Testing BOM")

    def test_needs_cleaning(self):
        self.assertTrue(identifier_needs_cleaning("['133']"))
        self.assertFalse(identifier_needs_cleaning("133"))


class CleanTaskIdsCommandTests(TestCase):
    def test_renames_bracket_wrapped_pk(self):
        from django.db import connection

        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO accounts_projecttask (project_id, description) VALUES (%s, %s)",
                ["['133']", "Legacy"],
            )
        fixed, skipped = clean_all_task_ids()
        self.assertEqual(fixed, 1)
        self.assertEqual(skipped, 0)
        self.assertTrue(ProjectTask.objects.filter(project_id="133").exists())
        self.assertFalse(ProjectTask.objects.filter(project_id="['133']").exists())

    def test_model_save_normalizes_on_create(self):
        task = ProjectTask(project_id="['NEW-001']", description="Auto clean")
        task.save()
        self.assertEqual(task.project_id, "NEW-001")
        self.assertTrue(ProjectTask.objects.filter(project_id="NEW-001").exists())
