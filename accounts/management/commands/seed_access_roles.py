from django.core.management.base import BaseCommand

from accounts.models import UserCategory
from accounts.roles import ROLE_DEFINITIONS


class Command(BaseCommand):
    help = "Seed or update the five Pioneer access categories (UserCategory)."

    def handle(self, *args, **options):
        for role in ROLE_DEFINITIONS:
            obj, created = UserCategory.objects.update_or_create(
                code=role["code"],
                defaults={
                    "description": role["description"],
                    "rank": role["rank"],
                    "role_summary": role["summary"],
                },
            )
            verb = "Created" if created else "Updated"
            self.stdout.write(f"{verb}: {obj.code} - {obj.description}")
        self.stdout.write(self.style.SUCCESS("Access categories ready."))