from decimal import Decimal

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

        try:
            from accounts.ledger import ensure_fund_control_accounts, fund_ceo_disbursement_account
            from django.contrib.auth import get_user_model

            ensure_fund_control_accounts()
            User = get_user_model()
            admin = User.objects.filter(is_superuser=True).order_by("id").first()
            if admin:
                fund_ceo_disbursement_account(
                    Decimal("1000000.00"),
                    admin,
                    memo="Bootstrap treasury funding of CEO disbursement account",
                )
            self.stdout.write(self.style.SUCCESS("Ledger control accounts OK."))
        except Exception as exc:
            self.stdout.write(self.style.WARNING(f"Ledger bootstrap skipped: {exc}"))
