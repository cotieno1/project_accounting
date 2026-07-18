from pathlib import Path

p = Path("accounts/emails.py")
text = p.read_text(encoding="utf-8")
old = '''def send_onboarding_email(user_account, *, request=None, invited_by=None):
    user = user_account.user
    if not user or not user_account.email:
        return False
    set_url = build_password_set_url(user, request=request)
    app_name = "Project Accounting"
    try:
        from .models import AppSettings
        app_name = AppSettings.get().app_name or app_name
    except Exception:
        pass
    inviter = ""
    if invited_by:
        inviter = getattr(invited_by, "get_full_name", lambda: "")() or getattr(invited_by, "username", "")
    context = {"app_name": app_name, "user": user, "user_account": user_account, "set_password_url": set_url, "invited_by": inviter, "role_name": (user_account.access_level.description if user_account.access_level else "User")}
    subject = f"{app_name} - set your password"
    text_body = render_to_string("emails/onboarding_set_password.txt", context)
    html_body = render_to_string("emails/onboarding_set_password.html", context)
    return send_system_email(subject=subject, to=[user_account.email], text_body=text_body, html_body=html_body, include_ceo_cc=False)'''
new = '''def send_onboarding_email(user_account, *, request=None, invited_by=None, record=True):
    user = user_account.user
    if not user or not user_account.email:
        if record:
            user_account.onboarding_email_last_error = "No login user or email address"
            user_account.save(update_fields=["onboarding_email_last_error"])
        return False
    set_url = build_password_set_url(user, request=request)
    app_name = "Project Accounting"
    try:
        from .models import AppSettings
        app_name = AppSettings.get().app_name or app_name
    except Exception:
        pass
    inviter = ""
    if invited_by:
        inviter = getattr(invited_by, "get_full_name", lambda: "")() or getattr(invited_by, "username", "")
    context = {"app_name": app_name, "user": user, "user_account": user_account, "set_password_url": set_url, "invited_by": inviter, "role_name": (user_account.access_level.description if user_account.access_level else "User")}
    subject = f"{app_name} - set your password"
    text_body = render_to_string("emails/onboarding_set_password.txt", context)
    html_body = render_to_string("emails/onboarding_set_password.html", context)
    ok = send_system_email(subject=subject, to=[user_account.email], text_body=text_body, html_body=html_body, include_ceo_cc=False)
    if record:
        from django.utils import timezone

        if ok:
            user_account.onboarding_email_sent_at = timezone.now()
            user_account.onboarding_email_last_error = ""
            user_account.save(update_fields=["onboarding_email_sent_at", "onboarding_email_last_error"])
        else:
            user_account.onboarding_email_last_error = "Email could not be sent (check SMTP settings)"
            user_account.save(update_fields=["onboarding_email_last_error"])
    return ok'''
if old not in text:
    raise SystemExit("pattern not found")
p.write_text(text.replace(old, new), encoding="utf-8")
print("ok nulls", p.read_bytes().count(b"\x00"))
