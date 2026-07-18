"""Register the State Department of Housing & Urban Development as a project sponsor.

Creates/updates the sponsor Organization (org_code SDHUD) with its accounting
officer (Principal Secretary Eng Charles Korir) and provisions a login account
for the PS so the sponsor can publish and manage tenders on the exchange.

Usage:
    python manage.py register_housing_sponsor
    python manage.py register_housing_sponsor --username ckorir --password "TempPass123!"
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts.models import Organization, UserAccount, UserCategory
from accounts.roles import USER_ADMIN

ORG_CODE = "SDHUD"
ORG_NAME = (
    "Ministry of Lands, Public Works, Housing and Urban Development - "
    "State Department of Housing and Urban Development"
)
ORG_SHORT = "State Dept. of Housing"
ORG_ADDRESS = (
    "Ministry of Lands, Public Works, Housing and Urban Development\n"
    "State Department of Housing and Urban Development\n"
    "P.O Box 30119-00100\n"
    "NAIROBI, KENYA"
)
OFFICER_NAME = "Eng Charles Korir"
OFFICER_TITLE = "Principal Secretary"
PROFILE_SUMMARY = (
    "The State Department of Housing and Urban Development, under the Ministry of "
    "Lands, Public Works, Housing and Urban Development, is the national accounting "
    "entity responsible for planning, financing and delivering the Affordable "
    "Housing Programme and associated urban infrastructure across Kenya. It "
    "publishes and manages works tenders on the BuildWatch exchange as the project "
    "sponsor / procuring entity."
)
WEBSITE = "https://housingandurban.go.ke"


class Command(BaseCommand):
    help = "Register State Department of Housing (SDHUD) sponsor org + PS login."

    def add_arguments(self, parser):
        parser.add_argument("--username", default="ckorir")
        parser.add_argument("--email", default="ps@housingandurban.go.ke")
        parser.add_argument(
            "--password",
            default="Housing#2026",
            help="Temporary password; the PS is forced to change it on first login.",
        )
        parser.add_argument("--staff-no", default="SDHUD-PS-001")

    @transaction.atomic
    def handle(self, *args, **opts):
        User = get_user_model()

        # 1) Sponsor organisation
        org, created = Organization.objects.get_or_create(
            org_code=ORG_CODE,
            defaults={
                "name": ORG_NAME,
                "short_name": ORG_SHORT,
                "contractor_type": Organization.CONTRACTOR_ROADS,
                "organization_type": "GOV_NATIONAL",
                "registration_status": Organization.STATUS_ACTIVE,
                "registered_address": ORG_ADDRESS,
                "contact_address": ORG_ADDRESS,
                "phone": "+254-020-2713833",
                "email": "info@housingandurban.go.ke",
                "document_tagline": "Affordable Housing Programme",
                "accounting_officer_name": OFFICER_NAME,
                "accounting_officer_title": OFFICER_TITLE,
                "profile_summary": PROFILE_SUMMARY,
                "website": WEBSITE,
            },
        )
        if not created:
            org.name = ORG_NAME
            org.short_name = ORG_SHORT
            org.organization_type = "GOV_NATIONAL"
            org.registration_status = Organization.STATUS_ACTIVE
            org.registered_address = ORG_ADDRESS
            org.contact_address = ORG_ADDRESS
            org.accounting_officer_name = OFFICER_NAME
            org.accounting_officer_title = OFFICER_TITLE
            org.profile_summary = PROFILE_SUMMARY
            org.website = WEBSITE
            org.save()
        self.stdout.write(self.style.SUCCESS(
            f"{'Created' if created else 'Updated'} sponsor org {ORG_CODE}: {ORG_NAME}"
        ))

        # 2) Org-admin role for the sponsor
        category, _ = UserCategory.objects.get_or_create(
            code=USER_ADMIN,
            defaults={"description": "User Admin (Global)", "rank": 100},
        )

        # 3) Principal Secretary login
        username = opts["username"].strip()
        email = opts["email"].strip()
        password = opts["password"]
        staff_no = opts["staff_no"].strip()

        user = User.objects.filter(username=username).first()
        if user is None:
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                first_name="Charles",
                last_name="Korir",
            )
        else:
            user.set_password(password)
            user.email = email
            user.first_name = "Charles"
            user.last_name = "Korir"
            user.save()

        ua = UserAccount.objects.filter(user=user).first()
        if ua is None:
            ua = UserAccount.objects.filter(staff_no=staff_no).first()
        if ua is None:
            ua = UserAccount(staff_no=staff_no)
        ua.user = user
        ua.first_name = "Charles"
        ua.last_name = "Korir"
        ua.designation = OFFICER_TITLE
        ua.contact_address = ORG_ADDRESS
        ua.phone = "+254-020-2713833"
        ua.email = email
        ua.access_level = category
        ua.organization = org
        ua.must_change_password = True
        ua.save()

        self.stdout.write(self.style.SUCCESS(
            f"Registered PS login: username='{username}' temp password='{password}' "
            f"(must change on first login)."
        ))
        self.stdout.write(
            f"Sponsor landing: /tenders/sponsors/{ORG_CODE}/   |   Accounting officer: "
            f"{OFFICER_TITLE} {OFFICER_NAME}"
        )
