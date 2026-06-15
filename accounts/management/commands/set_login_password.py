from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Set a user password directly (for Railway Console troubleshooting)."

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument("password")

    def handle(self, *args, **options):
        username = options["username"].strip()
        password = options["password"]
        User = get_user_model()
        user = User.objects.filter(username=username).first()
        if not user:
            user = User.objects.create_superuser(
                username=username,
                email="",
                password=password,
            )
            self.stdout.write(self.style.SUCCESS(f"Created superuser '{username}'."))
            return
        user.set_password(password)
        user.is_staff = True
        user.is_superuser = True
        user.is_active = True
        user.save()
        self.stdout.write(self.style.SUCCESS(f"Password updated for '{username}'."))