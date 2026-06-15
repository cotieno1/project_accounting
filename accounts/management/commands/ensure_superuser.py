import os

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

DEFAULT_USERNAME = "temp_admin"
DEFAULT_EMAIL = "otieno.charles@gmail.com"


def _read_env(*names):
    for name in names:
        value = os.environ.get(name)
        if value and value.strip():
            return value.strip()
    return ""


class Command(BaseCommand):
    help = "Create or update the Django superuser from environment variables."

    def handle(self, *args, **options):
        password = _read_env(
            "DJANGO_SUPERUSER_PASSWORD",
            "django_superuser_password",
            "BOOTSTRAP_ADMIN_PASSWORD",
        )
        username = _read_env("DJANGO_SUPERUSER_USERNAME", "django_superuser_username") or DEFAULT_USERNAME
        email = _read_env("DJANGO_SUPERUSER_EMAIL", "django_superuser_email") or DEFAULT_EMAIL

        db = settings.DATABASES["default"]
        engine = db.get("ENGINE", "")
        self.stdout.write(f"Database engine: {engine}")
        if "sqlite" in engine:
            self.stdout.write(self.style.WARNING(
                "Using SQLite on Railway — add DATABASE_URL from PostgreSQL or users will not persist."
            ))

        if not password:
            users = list(get_user_model().objects.values_list("username", flat=True))
            self.stdout.write(f"Known users: {users or '(none)'}")
            self.stdout.write(
                "Skipping ensure_superuser — set DJANGO_SUPERUSER_PASSWORD on the app service."
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
        else:
            User.objects.create_superuser(
                username=username,
                email=email,
                password=password,
            )
            self.stdout.write(self.style.SUCCESS(f"Created superuser '{username}'."))

        users = list(User.objects.values_list("username", flat=True))
        self.stdout.write(f"Known users after bootstrap: {users}")