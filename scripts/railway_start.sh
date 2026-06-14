#!/usr/bin/env bash
set -euo pipefail
python manage.py migrate --noinput
exec gunicorn UN_accounting_system.wsgi:application --bind "0.0.0.0:${PORT:-8000}"