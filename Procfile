web: python manage.py migrate --noinput && python manage.py collectstatic --noinput && python manage.py ensure_superuser && gunicorn UN_accounting_system.wsgi:application --bind 0.0.0.0:$PORT
