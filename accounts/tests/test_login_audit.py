from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings

from accounts.login_audit import resolve_ip_location
from accounts.models import LoginAuditEvent


@override_settings(ALLOWED_HOSTS=["testserver", "localhost"])
class LoginAuditTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="auditor", password="SecretPass123!")
        self.client = Client()

    def test_failed_login_is_recorded(self):
        with patch(
            "accounts.login_audit.resolve_ip_location",
            return_value={
                "location_label": "Local / private network",
                "country_code": "",
                "region": "",
                "city": "",
                "latitude": None,
                "longitude": None,
                "geo_source": "ip",
            },
        ):
            resp = self.client.post(
                "/login/",
                {"username": "auditor", "password": "wrong"},
            )
        self.assertEqual(resp.status_code, 200)
        ev = LoginAuditEvent.objects.order_by("-id").first()
        self.assertIsNotNone(ev)
        self.assertFalse(ev.success)
        self.assertEqual(ev.outcome, "failed")
        self.assertEqual(ev.username_attempted, "auditor")
        self.assertEqual(ev.location_label, "Local / private network")
        self.assertEqual(ev.geo_source, "ip")

    def test_successful_login_is_recorded(self):
        with patch(
            "accounts.login_audit.resolve_ip_location",
            return_value={
                "location_label": "Nairobi, Nairobi County, Kenya",
                "country_code": "KE",
                "region": "Nairobi County",
                "city": "Nairobi",
                "latitude": None,
                "longitude": None,
                "geo_source": "ip",
            },
        ):
            resp = self.client.post(
                "/login/",
                {"username": "auditor", "password": "SecretPass123!"},
            )
        self.assertIn(resp.status_code, (200, 302))
        ev = LoginAuditEvent.objects.filter(outcome="success").order_by("-id").first()
        self.assertIsNotNone(ev)
        self.assertTrue(ev.success)
        self.assertEqual(ev.username_attempted, "auditor")
        self.assertEqual(ev.user_id, self.user.id)
        self.assertIn("Nairobi", ev.location_label)
        self.assertEqual(ev.country_code, "KE")

    def test_private_ip_location_label(self):
        geo = resolve_ip_location("127.0.0.1")
        self.assertEqual(geo["location_label"], "Local / private network")
        self.assertEqual(geo["geo_source"], "ip")