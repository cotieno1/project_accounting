#!/usr/bin/env bash
set -uo pipefail

log() {
  echo "=== $* ==="
}

log "railway_start.sh begin"
log "Python: $(python --version 2>&1)"

if [ -n "${DATABASE_URL:-}" ]; then
  log "DATABASE_URL: set"
else
  log "DATABASE_URL: NOT SET (migrate will fail on Railway)"
fi

if [ -n "${RAILWAY_PUBLIC_DOMAIN:-}" ]; then
  log "RAILWAY_PUBLIC_DOMAIN: ${RAILWAY_PUBLIC_DOMAIN}"
fi

log "STEP 1/3: migrate"
if python manage.py migrate --noinput --verbosity 2; then
  log "STEP 1/3: migrate OK"
else
  log "STEP 1/3: migrate FAILED — starting web server anyway (home/login may work)"
fi

log "STEP 2/3: collectstatic"
if python manage.py collectstatic --noinput; then
  log "STEP 2/3: collectstatic OK"
else
  log "STEP 2/3: collectstatic FAILED — continuing"
fi

log "STEP 3/3: ensure superuser (optional)"
if [ -n "${DJANGO_SUPERUSER_PASSWORD:-${django_superuser_password:-}}" ]; then
  if python - <<'PY'
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
  then
    log "STEP 3/3: superuser OK"
  else
    log "STEP 3/3: superuser FAILED — continuing"
  fi
else
  log "STEP 3/3: superuser skipped (DJANGO_SUPERUSER_PASSWORD not set)"
fi

log "Starting gunicorn on 0.0.0.0:${PORT:-8000}"
exec gunicorn UN_accounting_system.wsgi:application \
  --bind "0.0.0.0:${PORT:-8000}" \
  --access-logfile - \
  --error-logfile - \
  --log-level info \
  --timeout 120
