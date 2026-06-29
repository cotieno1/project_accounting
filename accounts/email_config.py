"""Resolve Django EMAIL_BACKEND from environment (testable)."""


def resolve_email_backend(
    *,
    email_backend_override="",
    email_provider="",
    resend_api_key="",
    smtp_configured=False,
    debug=False,
):
    if email_backend_override:
        return email_backend_override
    provider = (email_provider or "").strip().lower()
    if provider == "resend" and resend_api_key:
        return "accounts.email_backends.ResendEmailBackend"
    if provider == "smtp" and smtp_configured:
        return "django.core.mail.backends.smtp.EmailBackend"
    if smtp_configured:
        return "django.core.mail.backends.smtp.EmailBackend"
    if resend_api_key:
        return "accounts.email_backends.ResendEmailBackend"
    if debug:
        return "django.core.mail.backends.console.EmailBackend"
    return "accounts.email_backends.UnconfiguredEmailBackend"