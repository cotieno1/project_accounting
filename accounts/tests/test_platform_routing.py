"""Platform Main Admin vs tenant portal routing."""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import Organization, UserAccount, UserCategory
from accounts.roles import SENIOR_SITE_MANAGER, USER_ADMIN


class PlatformRoutingTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.client = Client()
        UserCategory.objects.create(code=SENIOR_SITE_MANAGER, description="SSM", rank=30)
        UserCategory.objects.create(code=USER_ADMIN, description="Admin", rank=100)
        self.pioneer = Organization.objects.create(
            org_code="PIONEER",
            name="Pioneer Contractors Co Ltd",
            short_name="Pioneer",
            contractor_type=Organization.CONTRACTOR_BUILDING,
            registration_status=Organization.STATUS_ACTIVE,
        )
        pioneer_user = User.objects.create_user(username="pioneer1", password="test-pass-123")
        UserAccount.objects.create(
            user=pioneer_user,
            staff_no="P001",
            first_name="P",
            last_name="Staff",
            designation="Site Manager",
            contact_address="Site",
            phone="0",
            email="pioneer@example.com",
            organization=self.pioneer,
            access_level=UserCategory.objects.get(code=SENIOR_SITE_MANAGER),
        )
        admin_user = User.objects.create_user(username="mainadmin", password="test-pass-123")
        UserAccount.objects.create(
            user=admin_user,
            staff_no="ADM01",
            first_name="Main",
            last_name="Admin",
            designation="Platform Admin",
            contact_address="HQ",
            phone="0",
            email="admin@example.com",
            access_level=UserCategory.objects.get(code=USER_ADMIN),
        )

    def test_main_admin_login_redirects_to_platform(self):
        response = self.client.post(
            reverse("login"),
            {"username": "mainadmin", "password": "test-pass-123"},
        )
        self.assertRedirects(response, reverse("platform_admin"), fetch_redirect_response=False)

    def test_pioneer_staff_login_redirects_to_dashboard(self):
        response = self.client.post(
            reverse("login"),
            {"username": "pioneer1", "password": "test-pass-123"},
        )
        self.assertRedirects(response, reverse("dashboard"), fetch_redirect_response=False)

    def test_main_admin_dashboard_redirects_to_platform(self):
        self.client.login(username="mainadmin", password="test-pass-123")
        response = self.client.get(reverse("dashboard"))
        self.assertRedirects(response, reverse("platform_admin"))

    def test_pioneer_staff_platform_redirects_to_dashboard(self):
        self.client.login(username="pioneer1", password="test-pass-123")
        response = self.client.get(reverse("platform_admin"))
        self.assertRedirects(response, reverse("dashboard"))

    def test_platform_admin_shows_building_contractors(self):
        self.client.login(username="mainadmin", password="test-pass-123")
        response = self.client.get(reverse("platform_admin"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Building contractor tenants")
        self.assertContains(response, "PIONEER")

    def test_tenant_dashboard_shows_pioneer_command_center(self):
        self.client.login(username="pioneer1", password="test-pass-123")
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Command Center")
        self.assertContains(response, "Executive Overview")
        self.assertContains(response, "System &amp; Accounts Setup")