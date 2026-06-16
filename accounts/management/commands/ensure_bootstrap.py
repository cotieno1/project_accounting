from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = "Ensure minimum AppSettings and default Organization exist after migrate."

    def handle(self, *args, **options):
        if connection.vendor != "postgresql":
            self.stdout.write("Skipping ensure_bootstrap (not PostgreSQL).")
            return

        try:
            from accounts.models import AppSettings, Organization
        except Exception as exc:
            self.stdout.write(self.style.WARNING(f"Models unavailable: {exc}"))
            return

        try:
            AppSettings.get()
            self.stdout.write(self.style.SUCCESS("AppSettings OK."))
        except Exception as exc:
            self.stdout.write(self.style.ERROR(f"AppSettings failed: {exc}"))
            self.stdout.write("Run: python manage.py migrate --noinput")
            return

        try:
            if not Organization.objects.filter(org_code="PIONEER").exists():
                Organization.objects.create(
                    org_code="PIONEER",
                    name="Pioneer Contactors Co Ltd",
                    short_name="Pioneer",
                    contact_address="TCC Building, 6th floor, Taleex Junction, Mogadishu",
                    is_default=True,
                )
                self.stdout.write(self.style.SUCCESS("Created default organization PIONEER."))
            elif not Organization.objects.filter(is_default=True).exists():
                org = Organization.objects.order_by("org_code").first()
                if org:
                    org.is_default = True
                    org.save(update_fields=["is_default"])
                    self.stdout.write(self.style.SUCCESS(f"Marked {org.org_code} as default."))
            else:
                self.stdout.write("Default organization OK.")
        except Exception as exc:
            self.stdout.write(self.style.ERROR(f"Organization bootstrap failed: {exc}"))
            self.stdout.write("Run: python manage.py migrate --noinput")
