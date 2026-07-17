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

    def test_login_honours_next_to_bid_workspace(self):
        next_url = "/tenders/1/bid/"
        response = self.client.post(
            reverse("login") + f"?next={next_url}",
            {"username": "mainadmin", "password": "test-pass-123"},
        )
        self.assertRedirects(response, next_url, fetch_redirect_response=False)

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

    def test_platform_admin_defaults_to_executive_overview(self):
        self.client.login(username="mainadmin", password="test-pass-123")
        response = self.client.get(reverse("platform_admin"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Command Center")
        self.assertContains(response, "Cost Performance (CPI)")
        self.assertContains(response, "showSection('overview')")
        self.assertContains(response, "Building contractor tenants")

    def test_platform_admin_shows_building_contractors_tab(self):
        self.client.login(username="mainadmin", password="test-pass-123")
        response = self.client.get(reverse("platform_admin"))
        self.assertContains(response, "Building Contractors")
        self.assertContains(response, "PIONEER")

    def test_platform_admin_hides_bracketed_pioneer_duplicate(self):
        Organization.objects.create(
            org_code="['PIONEER']",
            name="['Pioneer Construction Co Ltd']",
            short_name="['Pioneer']",
            contractor_type=Organization.CONTRACTOR_BUILDING,
            registration_status=Organization.STATUS_ACTIVE,
        )
        self.client.login(username="mainadmin", password="test-pass-123")
        response = self.client.get(reverse("platform_admin"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "PIONEER")
        self.assertContains(response, "Pioneer Contactors Co Ltd")
        self.assertNotContains(response, "['PIONEER']")
        self.assertNotContains(response, "['Pioneer']")
        self.assertEqual(response.content.decode().count("Pioneer Contactors Co Ltd"), 1)

    def test_tenant_dashboard_shows_pioneer_command_center(self):
        self.client.login(username="pioneer1", password="test-pass-123")
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Command Center")
        self.assertContains(response, "Executive Overview")
        self.assertContains(response, "System &amp; Accounts Setup")

    def test_platform_admin_shows_subscriber_workspace_selector(self):
        Organization.objects.create(
            org_code="QS_FIRM",
            name="Quality Surveyors Ltd",
            short_name="QS Firm",
            contractor_type=Organization.CONTRACTOR_CONSULTANT,
            organization_type="QS",
            registration_status=Organization.STATUS_ACTIVE,
        )
        Organization.objects.create(
            org_code="ISIOLO",
            name="County Government of Isiolo",
            short_name="Isiolo County",
            contractor_type=Organization.CONTRACTOR_ROADS,
            organization_type="GOV_COUNTY",
            registration_status=Organization.STATUS_ACTIVE,
        )
        self.client.login(username="mainadmin", password="test-pass-123")
        response = self.client.get(reverse("platform_admin"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Subscriber workspace")
        self.assertContains(response, "Select contractor")
        self.assertContains(response, "Select consultant")
        self.assertContains(response, "Projects &amp; sponsors")
        self.assertNotContains(response, "Platform admin — switch organization")
        self.assertNotContains(response, 'id="orgSwitcher"')

    def test_platform_admin_can_switch_contractor_workspace(self):
        self.client.login(username="mainadmin", password="test-pass-123")
        response = self.client.post(
            reverse("switch_active_organization"),
            {"workspace_target": f"contractor:{self.pioneer.org_code}"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "success")
        self.assertEqual(self.client.session.get("active_workspace_kind"), "contractor")

    def test_ops_dashboard_back_link_for_main_admin(self):
        self.client.login(username="mainadmin", password="test-pass-123")
        response = self.client.get(reverse("ops_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("platform_admin"))