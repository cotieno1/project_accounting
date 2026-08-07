from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings

from accounts.models import LoginAuditEvent


@override_settings(ALLOWED_HOSTS=["testserver", "localhost"])
class LoginAuditTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="auditor", password="SecretPass123!")
        self.client = Client()

    def test_failed_login_is_recorded(self):
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

    def test_successful_login_is_recorded(self):
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