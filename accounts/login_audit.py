"""Helpers and auth-signal handlers for login incident detection."""
from __future__ import annotations

import logging

from django.contrib.auth.signals import user_logged_in, user_login_failed
from django.dispatch import receiver

logger = logging.getLogger("accounts.login_audit")


def client_ip(request):
    if request is None:
        return None
    forwarded = (request.META.get("HTTP_X_FORWARDED_FOR") or "").strip()
    if forwarded:
        return forwarded.split(",")[0].strip()[:45] or None
    remote = (request.META.get("REMOTE_ADDR") or "").strip()
    return remote[:45] or None


def client_user_agent(request):
    if request is None:
        return ""
    return (request.META.get("HTTP_USER_AGENT") or "")[:400]


def record_login_event(
    *,
    request=None,
    username="",
    user=None,
    success=False,
    outcome="failed",
    detail="",
):
    from .models import LoginAuditEvent

    ip = client_ip(request)
    ua = client_user_agent(request)
    path = ""
    if request is not None:
        path = (getattr(request, "path", None) or "")[:200]
    username = (username or "").strip()[:150]
    if not username and user is not None:
        username = (getattr(user, "username", None) or "")[:150]

    try:
        LoginAuditEvent.objects.create(
            username_attempted=username,
            user=user if getattr(user, "pk", None) else None,
            success=bool(success),
            outcome=outcome,
            ip_address=ip,
            user_agent=ua,
            path=path,
            detail=(detail or "")[:255],
        )
    except Exception:
        logger.exception("Failed to persist login audit event")
        return

    logger.info(
        "login_audit outcome=%s user=%r ip=%s path=%s detail=%r",
        outcome,
        username,
        ip,
        path,
        detail,
    )


@receiver(user_logged_in)
def _on_user_logged_in(sender, request, user, **kwargs):
    record_login_event(
        request=request,
        username=getattr(user, "username", "") or "",
        user=user,
        success=True,
        outcome="success",
    )


@receiver(user_login_failed)
def _on_user_login_failed(sender, credentials, request, **kwargs):
    username = ""
    if isinstance(credentials, dict):
        username = credentials.get("username") or credentials.get("email") or ""
    record_login_event(
        request=request,
        username=str(username or ""),
        user=None,
        success=False,
        outcome="failed",
    )