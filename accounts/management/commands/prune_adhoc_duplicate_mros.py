from django.core.management.base import BaseCommand
from accounts.models import ProjectTask
from accounts.views import _prune_duplicate_adhoc_mros


class Command(BaseCommand):
    help = "Remove duplicate ad-hoc MRO ledger rows after accidental double budget commit."

    def add_arguments(self, parser):
        parser.add_argument("--task-id", dest="task_id", help="Limit cleanup to one task project_id")

    def handle(self, *args, **options):
        task_id = options.get("task_id")
        tasks = ProjectTask.objects.all()
        if task_id:
            tasks = tasks.filter(project_id=task_id)
        total_removed = 0
        for task in tasks:
            removed = _prune_duplicate_adhoc_mros(task)
            if removed:
                total_removed += len(removed)
                self.stdout.write(
                    self.style.WARNING(
                        f"{task.project_id}: removed duplicate MRO(s) {', '.join(removed)}"
                    )
                )
        if not total_removed:
            self.stdout.write(self.style.SUCCESS("No duplicate ad-hoc MRO rows found."))
