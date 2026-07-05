"""BuildWatch self-service contractor registration tests."""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import Organization, UserAccount, UserCategory
from accounts.roles import SENIOR_SITE_MANAGER, USER_ADMIN


class BuildWatchRegistrationTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.client = Client()
        UserCategory.objects.create(code=SENIOR_SITE_MANAGER, description="SSM", rank=30)
        UserCategory.objects.create(code=USER_ADMIN, description="Admin", rank=100)
        Organization.objects.create(
            org_code="PIONEER",
            name="Pioneer Contractors Co Ltd",
            short_name="Pioneer",
            contractor_type=Organization.CONTRACTOR_BUILDING,
            registration_status=Organization.STATUS_ACTIVE,
        )

    def _registration_payload(self, **overrides):
        data = {
            "org_name": "New Roads Contractor Ltd",
            "org_short": "RoadsCo",
            "org_type": "CONTRACTOR",
            "contractor_category": "ROADS",
            "org_country": "KE",
            "org_county": "Nairobi",
            "org_pin": "P051234567X",
            "org_phone": "+254700000001",
            "org_address": "Nairobi",
            "user_first": "Jane",
            "user_last": "Contractor",
            "user_email": "jane.contractor@example.com",
            "user_phone": "+254711111111",
            "user_designation": "Site Engineer",
            "buildwatch_role": "CONTRACTOR",
            "licence_body": "NCA",
            "licence_no": "NCA-12345",
            "licence_expiry": "2027-12-31",
            "licence_class": "Building",
            "tos_agreed": "1",
        }
        data.update(overrides)
        return data

    def test_register_get_prefill_pioneer(self):
        response = self.client.get(reverse("buildwatch-register") + "?org=PIONEER")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Pioneer")

    def test_buildwatch_home_landing(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "BuildWatch")
        self.assertContains(response, "Select contractor category")
        self.assertContains(response, "Select consultant discipline")
        self.assertNotContains(response, "Join Pioneer")

    def test_register_get_prefill_contractor_category(self):
        response = self.client.get(
            reverse("buildwatch-register") + "?track=contractor&category=AIRPORT"
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "CONTRACTOR")
        self.assertContains(response, "AIRPORT")

    def test_new_org_registration_is_pending(self):
        response = self.client.post(
            reverse("buildwatch-register"),
            self._registration_payload(),
        )
        self.assertEqual(response.status_code, 302)
        org = Organization.objects.get(short_name="RoadsCo")
        self.assertEqual(org.registration_status, Organization.STATUS_PENDING)
        ua = UserAccount.objects.get(email="jane.contractor@example.com")
        self.assertTrue(ua.registration_pending_review)

    def test_pioneer_join_auto_links_active_org(self):
        response = self.client.post(
            reverse("buildwatch-register"),
            self._registration_payload(
                org_name="Pioneer Contractors Co Ltd",
                org_short="Pioneer",
                contractor_category="BUILDING",
                user_email="pioneer.new@example.com",
            ),
        )
        self.assertEqual(response.status_code, 302)
        ua = UserAccount.objects.get(email="pioneer.new@example.com")
        self.assertEqual(ua.organization.org_code, "PIONEER")
        self.assertFalse(ua.registration_pending_review)

    def test_approve_pending_registration(self):
        self.client.post(reverse("buildwatch-register"), self._registration_payload())
        User = get_user_model()
        admin = User.objects.create_user(username="admin1", password="test-pass-123")
        UserAccount.objects.create(
            user=admin,
            staff_no="ADM01",
            first_name="A",
            last_name="D",
            designation="Admin",
            contact_address="HQ",
            phone="0",
            email="admin@example.com",
            access_level=UserCategory.objects.get(code=USER_ADMIN),
        )
        self.client.login(username="admin1", password="test-pass-123")
        response = self.client.post(
            reverse("approve_buildwatch_registration"),
            {"email": "jane.contractor@example.com"},
        )
        self.assertEqual(response.status_code, 200)
        ua = UserAccount.objects.get(email="jane.contractor@example.com")
        self.assertFalse(ua.registration_pending_review)
        org = Organization.objects.get(short_name="RoadsCo")
        self.assertEqual(org.registration_status, Organization.STATUS_ACTIVE)