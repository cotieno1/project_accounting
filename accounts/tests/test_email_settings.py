from types import SimpleNamespace

from django.test import SimpleTestCase, override_settings

from accounts.email_config import resolve_email_backend
from accounts.emails import _branded_from_email, _normalize_display_label

class EmailBackendResolverTests(SimpleTestCase):
    def test_smtp_preferred_when_configured_even_with_resend_key(self):
        backend = resolve_email_backend(
            resend_api_key="re_abc",
            smtp_configured=True,
        )
        self.assertEqual(backend, "django.core.mail.backends.smtp.EmailBackend")

    def test_resend_when_provider_resend_and_no_smtp(self):
        backend = resolve_email_backend(
            email_provider="resend",
            resend_api_key="re_abc",
            smtp_configured=False,
        )
        self.assertEqual(backend, "accounts.email_backends.ResendEmailBackend")

    def test_smtp_when_provider_smtp(self):
        backend = resolve_email_backend(
            email_provider="smtp",
            smtp_configured=True,
        )
        self.assertEqual(backend, "django.core.mail.backends.smtp.EmailBackend")

    def test_unconfigured_in_production_without_providers(self):
        backend = resolve_email_backend(
            smtp_configured=False,
            resend_api_key="",
            debug=False,
        )
        self.assertEqual(backend, "accounts.email_backends.UnconfiguredEmailBackend")


class EmailDisplayLabelTests(SimpleTestCase):
    def test_normalize_bracketed_list_string(self):
        self.assertEqual(_normalize_display_label("['Pioneer']"), "Pioneer")

    def test_normalize_plain_name(self):
        self.assertEqual(_normalize_display_label("Pioneer"), "Pioneer")

    def test_normalize_list_value(self):
        self.assertEqual(_normalize_display_label(["Pioneer"]), "Pioneer")


@override_settings(DEFAULT_FROM_EMAIL="Project Accounting <otieno.charles@gmail.com>")
class BrandedFromEmailTests(SimpleTestCase):
    def test_bracketed_short_name_produces_valid_from(self):
        org = SimpleNamespace(short_name="['Pioneer']", name="Pioneer Contactors Co Ltd")
        self.assertEqual(
            _branded_from_email(org),
            "Pioneer <otieno.charles@gmail.com>",
        )

    def test_plain_short_name(self):
        org = SimpleNamespace(short_name="Pioneer", name="Pioneer Contactors Co Ltd")
        self.assertEqual(
            _branded_from_email(org),
            "Pioneer <otieno.charles@gmail.com>",
        )