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

if [ -n "${RESEND_API_KEY:-}" ]; then
  log "Platform email (all companies): Resend API key is set"
elif [ -n "${EMAIL_HOST_USER:-}" ] && [ -n "${EMAIL_HOST_PASSWORD:-}" ]; then
  log "Platform email (all companies): SMTP configured (${EMAIL_HOST:-localhost})"
else
  log "Platform email (all companies): NOT CONFIGURED — add RESEND_API_KEY or SMTP vars on this Railway service"
fi

log "STEP 1/3: migrate"
if python manage.py migrate --noinput --verbosity 2; then
  log "STEP 1/3: migrate OK"
else
  log "STEP 1/3: migrate FAILED — check deploy logs; dashboard may show setup message"
fi

log "STEP 1b: ensure_bootstrap"
if python manage.py ensure_bootstrap; then
  log "STEP 1b: ensure_bootstrap OK"
else
  log "STEP 1b: ensure_bootstrap FAILED — continuing"
fi

log "STEP 1c: quality scorecard"
QUALITY_MIN="${QUALITY_MIN_SCORE:-90}"
if python manage.py quality_scorecard --min-score "$QUALITY_MIN"; then
  log "STEP 1c: quality scorecard OK (>= ${QUALITY_MIN}%)"
else
  log "STEP 1c: quality scorecard FAILED (< ${QUALITY_MIN}%)"
  if [ "${BLOCK_DEPLOY_ON_QUALITY_FAILURE:-}" = "1" ]; then
    log "BLOCK_DEPLOY_ON_QUALITY_FAILURE=1 — aborting deploy"
    exit 1
  fi
fi

if [ "${RUN_TESTS_ON_DEPLOY:-}" = "1" ]; then
  log "STEP 1d: regression tests"
  if python manage.py test accounts.tests --verbosity 1; then
    log "STEP 1d: regression tests OK"
  else
    log "STEP 1d: regression tests FAILED"
    if [ "${BLOCK_DEPLOY_ON_TEST_FAILURE:-}" = "1" ]; then
      exit 1
    fi
  fi
fi

log "STEP 2/3: collectstatic"
if python manage.py collectstatic --noinput; then
  log "STEP 2/3: collectstatic OK"
else
  log "STEP 2/3: collectstatic FAILED — continuing"
fi

log "STEP 3/3: ensure superuser (optional)"
if [ -n "${DJANGO_SUPERUSER_PASSWORD:-${django_superuser_password:-}}" ]; then
  if python manage.py ensure_superuser; then
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
