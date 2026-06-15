#!/usr/bin/env bash
set -euo pipefail
python manage.py migrate --noinput
if [ -n "${DJANGO_SUPERUSER_PASSWORD:-${django_superuser_password:-}}" ]; then
  python - <<'PY'
import os
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "UN_accounting_system.settings")
django.setup()
from django.contrib.auth import get_user_model
User = get_user_model()
username = os.environ.get("DJANGO_SUPERUSER_USERNAME") or os.environ.get("django_superuser_username") or "temp_admin"
password = os.environ.get("DJANGO_SUPERUSER_PASSWORD") or os.environ.get("django_superuser_password") or ""
email = os.environ.get("DJANGO_SUPERUSER_EMAIL") or os.environ.get("django_superuser_email") or "otieno.charles@gmail.com"
if password:
    user = User.objects.filter(username=username).first()
    if user:
        user.set_password(password)
        user.email = email or user.email
        user.is_staff = user.is_superuser = user.is_active = True
        user.save()
        print(f"Updated superuser: {username}")
    else:
        User.objects.create_superuser(username, email, password)
        print(f"Created superuser: {username}")
PY
fi
exec gunicorn UN_accounting_system.wsgi:application --bind "0.0.0.0:${PORT:-8000}"