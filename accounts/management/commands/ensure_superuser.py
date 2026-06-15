import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

DEFAULT_USERNAME = "temp_admin"
DEFAULT_EMAIL = "otieno.charles@gmail.com"


class Command(BaseCommand):
    help = "Create or update the Django superuser from environment variables."

    def handle(self, *args, **options):
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD", "").strip()
        username = os.environ.get("DJANGO_SUPERUSER_USERNAME", DEFAULT_USERNAME).strip()
        email = os.environ.get("DJANGO_SUPERUSER_EMAIL", DEFAULT_EMAIL).strip()

        if not password:
            self.stdout.write(
                "Skipping ensure_superuser (set DJANGO_SUPERUSER_PASSWORD in Railway)."
            )
            return

        User = get_user_model()
        user = User.objects.filter(username=username).first()
        if user:
            user.set_password(password)
            user.email = email or user.email
            user.is_staff = True
            user.is_superuser = True
            user.is_active = True
            user.save()
            self.stdout.write(self.style.SUCCESS(f"Updated superuser '{username}'."))
            return

        User.objects.create_superuser(
            username=username,
            email=email,
            password=password,
        )
        self.stdout.write(self.style.SUCCESS(f"Created superuser '{username}'."))