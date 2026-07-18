"""Outbound email helpers: onboarding, notifications, CEO CC on all mail."""

import ast
import logging

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from .roles import PERM_GRN_EMAIL, PERM_NOTIFY_MISC_PO_APPROVED, ceo_cc_emails, user_can

logger = logging.getLogger(__name__)


def _friendly_email_error(exc):
    err = str(exc).strip() or exc.__class__.__name__
    lowered = err.lower()
    if (
        "errno 111" in lowered
        or "connection refused" in lowered
        or "10061" in err
        or "connection failed" in lowered
    ):
        if not getattr(settings, "EMAIL_CONFIGURED", False):
            return (
                "Platform email is not configured. In Railway → Variables, set Gmail SMTP: "
                "EMAIL_HOST_USER=your@gmail.com, EMAIL_HOST_PASSWORD=16-char app password, "
                "EMAIL_HOST=smtp.gmail.com, EMAIL_PORT=587, EMAIL_USE_TLS=True."
            )
        host = getattr(settings, "EMAIL_HOST", "localhost")
        port = getattr(settings, "EMAIL_PORT", 587)
        return (
            f"Could not connect to mail server {host}:{port}. "
            "Check EMAIL_HOST and EMAIL_PORT."
        )
    if "535" in err or "534" in err or "authentication failed" in lowered or "username and password" in lowered:
        return (
            "Gmail rejected the login. Use a Google App Password (not your normal Gmail password): "
            "Google Account → Security → 2-Step Verification → App passwords."
        )
    if "daily user sending limit" in lowered or "limit exceeded" in lowered:
        return (
            "Gmail sending limit reached for today. Try again later or use a Google Workspace account."
        )
    return err


def _site_base_url(request=None):
    if request:
        return request.build_absolute_uri("/").rstrip("/")
    base = getattr(settings, "SITE_BASE_URL", "").strip()
    if base:
        return base.rstrip("/")
    return "http://127.0.0.1:8000"


def build_password_set_url(user, request=None):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    base = _site_base_url(request)
    return f"{base}/accounts/set-password/{uid}/{token}/"


def send_system_email(*, subject, to, text_body, html_body=None, cc=None, include_ceo_cc=True, reply_to=None, from_email=None):
    """Send one system email. Returns (success, error_message)."""
    recipients = [e.strip() for e in (to if isinstance(to, (list, tuple)) else [to]) if e and e.strip()]
    if not recipients:
        logger.warning("send_system_email skipped: no recipients (%s)", subject)
        return False, "No recipient email address"
    cc_list = [e.strip() for e in (cc or []) if e and e.strip()]
    if include_ceo_cc:
        for addr in ceo_cc_emails():
            if addr not in recipients and addr not in cc_list:
                cc_list.append(addr)
    from_email = from_email or getattr(settings, "DEFAULT_FROM_EMAIL", None) or "noreply@localhost"
    msg = EmailMultiAlternatives(subject=subject, body=text_body, from_email=from_email, to=recipients, cc=cc_list or None, reply_to=[reply_to] if reply_to else None)
    if html_body:
        msg.attach_alternative(html_body, "text/html")
    try:
        msg.send(fail_silently=False)
        return True, ""
    except Exception as exc:
        err = _friendly_email_error(exc)
        if len(err) > 320:
            err = err[:320] + "..."
        logger.exception("send_system_email failed: %s", exc)
        return False, err


def _normalize_display_label(raw):
    """Turn org short_name/name into a safe RFC display name (not a Python list repr)."""
    if raw is None:
        return ""
    if isinstance(raw, (list, tuple)):
        for item in raw:
            label = _normalize_display_label(item)
            if label:
                return label
        return ""
    s = str(raw).strip()
    if not s:
        return ""
    if s.startswith("[") and s.endswith("]"):
        try:
            parsed = ast.literal_eval(s)
            if isinstance(parsed, (list, tuple)) and parsed:
                return _normalize_display_label(parsed[0])
            if isinstance(parsed, str):
                return parsed.strip()
        except (ValueError, SyntaxError):
            inner = s[1:-1].strip().strip("'\"")
            if inner:
                return inner.split(",")[0].strip().strip("'\"")
    return s.strip("'\"[]")


def _branded_from_email(organization=None):
    """Use company name in the From display name; address stays the platform DEFAULT_FROM_EMAIL."""
    base = getattr(settings, "DEFAULT_FROM_EMAIL", None) or "noreply@localhost"
    org_label = ""
    if organization:
        org_label = _normalize_display_label(
            organization.short_name or organization.name or ""
        )
    if org_label and "@" in base:
        if "<" in base and ">" in base:
            addr = base.split("<", 1)[1].rstrip(">").strip()
            return f"{org_label} <{addr}>"
        return f"{org_label} <{base}>"
    return base


def send_onboarding_email(user_account, *, request=None, invited_by=None, record=True):
    user = user_account.user
    if not user or not user_account.email:
        if record:
            user_account.onboarding_email_last_error = "No login user or email address"
            user_account.save(update_fields=["onboarding_email_last_error"])
        return False, "No login user or email address"
    set_url = build_password_set_url(user, request=request)
    app_name = "Project Accounting"
    try:
        from .models import AppSettings
        app_name = AppSettings.get().app_name or app_name
    except Exception:
        pass
    org = getattr(user_account, "organization", None)
    org_name = (org.name if org else "") or app_name
    inviter = ""
    if invited_by:
        inviter = getattr(invited_by, "get_full_name", lambda: "")() or getattr(invited_by, "username", "")
    context = {
        "app_name": app_name,
        "org_name": org_name,
        "user": user,
        "user_account": user_account,
        "set_password_url": set_url,
        "invited_by": inviter,
        "role_name": (user_account.access_level.description if user_account.access_level else "User"),
    }
    subject = f"{org_name} — set your password"
    text_body = render_to_string("emails/onboarding_set_password.txt", context)
    html_body = render_to_string("emails/onboarding_set_password.html", context)
    reply_to = (org.email if org and org.email else None) or getattr(settings, "EMAIL_HOST_USER", "") or getattr(settings, "SYSTEM_ADMIN_EMAIL", "")
    ok, err = send_system_email(
        subject=subject,
        to=[user_account.email],
        text_body=text_body,
        html_body=html_body,
        include_ceo_cc=False,
        reply_to=reply_to,
        from_email=_branded_from_email(org),
    )
    if record:
        from django.utils import timezone

        if ok:
            user_account.onboarding_email_sent_at = timezone.now()
            user_account.onboarding_email_last_error = ""
            user_account.save(update_fields=["onboarding_email_sent_at", "onboarding_email_last_error"])
        else:
            user_account.onboarding_email_last_error = err or "Email could not be sent (check SMTP settings)"
            user_account.save(update_fields=["onboarding_email_last_error"])
    return ok, err


def notify_misc_po_approved(user, *, task_id, mro_ref, amount_display, view_url):
    if not user_can(user, PERM_NOTIFY_MISC_PO_APPROVED):
        return False
    ua = getattr(user, "useraccount", None)
    email = ua.email if ua else user.email
    if not email:
        return False
    subject = f"Misc PO approved - {mro_ref}"
    text_body = f"Your Misc PO {mro_ref} on task {task_id} has been approved.\nAmount: {amount_display}\nView: {view_url}\n"
    ok, _err = send_system_email(subject=subject, to=[email], text_body=text_body)
    return ok


def notify_grn_received(user, *, grn_ref, task_id, view_url):
    if not user_can(user, PERM_GRN_EMAIL):
        return False
    ua = getattr(user, "useraccount", None)
    email = ua.email if ua else user.email
    if not email:
        return False
    subject = f"GRN recorded - {grn_ref}"
    text_body = f"Goods receipt {grn_ref} for task {task_id} is recorded.\nView: {view_url}\n"
    ok, _err = send_system_email(subject=subject, to=[email], text_body=text_body)
    return ok


def notify_budget_variance(*, task_id, budget_display, actual_display, variance_display):
    from .models import UserAccount
    ceo_accounts = UserAccount.objects.filter(access_level__code="CEO").exclude(email="")
    emails = [a.email for a in ceo_accounts if a.email]
    if not emails:
        return False
    subject = f"Budget variance alert - task {task_id}"
    text_body = f"Task {task_id} budget variance requires review.\nBudget: {budget_display}\nActual: {actual_display}\nVariance: {variance_display}\n"
    ok, _err = send_system_email(subject=subject, to=emails, text_body=text_body, include_ceo_cc=False)
    return ok


def send_grn_admin_copy(grn, request, *, print_context):
    """Email GRN summary + print link to system admin (GM disbursement workflow)."""
    from django.urls import reverse

    from .roles import system_admin_emails

    recipients = system_admin_emails()
    if not recipients:
        logger.warning("send_grn_admin_copy skipped: no system admin email configured")
        return False

    task = print_context["task"]
    lpo = print_context["lpo"]
    supplier = print_context.get("supplier")
    supplier_name = supplier.description if supplier else "Supplier"
    print_url = request.build_absolute_uri(
        reverse("print_grn_view", args=[grn.id]) + "?print=1&back=gm"
    )
    gm_url = request.build_absolute_uri(
        reverse("gm_aie_disbursement") + f"?task_id={task.project_id}&open_grn_period=1"
    )
    triggered_by = request.user.get_full_name() or request.user.username

    subject = f"GRN copy for your attention — {grn.grn_no} · Task {task.project_id}"
    text_body = (
        f"A Goods Received Note was printed from GM Disbursement.\n\n"
        f"GRN: {grn.grn_no}\n"
        f"LPO: {lpo.lpo_no}\n"
        f"Task: {task.project_id} — {task.description}\n"
        f"Supplier: {supplier_name}\n"
        f"Invoice: {grn.invoice_ref or '—'}\n"
        f"Receipt date: {print_context.get('receipt_date_display', grn.receipt_date)}\n"
        f"Total invoiced: US$ {print_context.get('receipt_total', '0.00')}\n"
        f"Delivery: {'FULL' if print_context.get('is_full_delivery') else 'PARTIAL'}\n"
        f"Recorded by: {triggered_by}\n\n"
        f"Print GRN: {print_url}\n"
        f"GM Disbursement: {gm_url}\n"
    )
    ok, _err = send_system_email(
        subject=subject,
        to=recipients,
        text_body=text_body,
        include_ceo_cc=False,
    )
    return ok
