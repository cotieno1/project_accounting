"""Access tests for fund ledger CEO/GM screen."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import ProjectTask, UserCategory
from accounts.roles import CEO, GENERAL_MANAGER, REGULAR_USER


class FundLedgerAccessTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.ceo_cat = UserCategory.objects.create(code=CEO, description="CEO", rank=80)
        self.gm_cat = UserCategory.objects.create(code=GENERAL_MANAGER, description="GM", rank=50)
        self.reg_cat = UserCategory.objects.create(code=REGULAR_USER, description="Regular", rank=10)

        self.ceo = User.objects.create_user(username="ceo_ledger", password="test-pass-123")
        self.gm = User.objects.create_user(username="gm_ledger", password="test-pass-123")
        self.reg = User.objects.create_user(username="reg_ledger", password="test-pass-123")

        from accounts.models import UserAccount

        UserAccount.objects.create(
            user=self.ceo, staff_no="CEO01", first_name="C", last_name="EO",
            designation="CEO", contact_address="HQ", phone="000", email="ceo@test.local",
            access_level=self.ceo_cat,
        )
        UserAccount.objects.create(
            user=self.gm, staff_no="GM01", first_name="G", last_name="M",
            designation="GM", contact_address="HQ", phone="000", email="gm@test.local",
            access_level=self.gm_cat,
        )
        UserAccount.objects.create(
            user=self.reg, staff_no="REG01", first_name="R", last_name="U",
            designation="Staff", contact_address="HQ", phone="000", email="reg@test.local",
            access_level=self.reg_cat,
        )

        ProjectTask.objects.create(project_id="LEDGER-VIEW", description="Ledger view test")

    def test_ceo_can_open_fund_ledger(self):
        self.client.login(username="ceo_ledger", password="test-pass-123")
        response = self.client.get(reverse("fund_ledger"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Fund Control Ledger")

    def test_gm_can_open_fund_ledger(self):
        self.client.login(username="gm_ledger", password="test-pass-123")
        response = self.client.get(reverse("print_fund_ledger"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "CEO Disbursement")

    def test_regular_user_denied(self):
        self.client.login(username="reg_ledger", password="test-pass-123")
        response = self.client.get(reverse("fund_ledger"))
        self.assertEqual(response.status_code, 403)
