#!/usr/bin/env bash
set -euo pipefail

echo "=== Railway boot ==="
echo "PORT=${PORT:-not set}"
if [ -n "${DATABASE_URL:-}" ]; then
  echo "DATABASE_URL is set"
else
  echo "ERROR: DATABASE_URL is not set on this service"
  exit 1
fi

echo "=== migrate ==="
python manage.py migrate --noinput

echo "=== collectstatic ==="
python manage.py collectstatic --noinput

echo "=== ensure_superuser ==="
python manage.py ensure_superuser || echo "ensure_superuser skipped"

echo "=== gunicorn on 0.0.0.0:${PORT:-8080} ==="
exec gunicorn UN_accounting_system.wsgi:application \
  --bind "0.0.0.0:${PORT:-8080}" \
  --workers 2 \
  --timeout 120 \
  --log-level info \
  --access-logfile - \
  --error-logfile -