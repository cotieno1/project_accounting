#!/usr/bin/env bash
set -euo pipefail
python manage.py migrate --noinput
python manage.py ensure_superuser
exec gunicorn UN_accounting_system.wsgi:application --bind "0.0.0.0:${PORT:-8000}"