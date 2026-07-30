# -*- coding: utf-8 -*-
"""Register MTN South Sudan as telecom sponsor + main contractor.

Creates:
  - Country: South Sudan
  - Sponsor org MTNSS (PRIVATE project owner) for conceptualization
  - Contractor org MTNTEL (TELECOM infrastructure) as main contractor
  - ICT InfraProject in conceptualization phase
  - Login Weshiwani (W. Eshiwani) as Senior Site Engineer on the sponsor org (MTN employee)

Usage:
    python manage.py register_mtn_south_sudan_telecom
    python manage.py register_mtn_south_sudan_telecom --password "TempPass123!"
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import Organization, ProjectTask, UserAccount, UserCategory
from accounts.roles import SENIOR_SITE_MANAGER


SPONSOR_CODE = "MTNSS"
SPONSOR_NAME = "MTN South Sudan"
SPONSOR_SHORT = "MTN South Sudan"

CONTRACTOR_CODE = "MTNTEL"
CONTRACTOR_NAME = "MTN South Sudan - Telecom Infrastructure"
CONTRACTOR_SHORT = "MTN Telecom"

ORG_ADDRESS = (
    "MTN South Sudan\n"
    "Juba, Central Equatoria\n"
    "Republic of South Sudan"
)
PROFILE_SPONSOR = (
    "MTN South Sudan is the project sponsor / corporate owner for telecom "
    "infrastructure programmes in South Sudan. Current initiatives are in the "
    "Project Concept (inception) phase on BuildWatch before design and "
    "procurement packages are published."
)
PROFILE_CONTRACTOR = (
    "MTN South Sudan registered as the main telecom infrastructure contractor "
    "for its own South Sudan network programmes (owner-operator / self-perform). "
    "Category: Telecom infrastructure."
)
PROJECT_ID = "MTN-SSD-TEL-001"
PROJECT_TITLE = "MTN South Sudan - National Telecom Infrastructure Programme"


class Command(BaseCommand):
    help = (
        "Register MTN South Sudan as telecom project sponsor + main contractor, "
        "with W. Eshiwani (Weshiwani) as Senior Site Engineer."
    )

    def add_arguments(self, parser):
        parser.add_argument("--username", default="weshiwani")
        parser.add_argument("--email", default="w.eshiwani@mtn.com.ss")
        parser.add_argument(
            "--password",
            default="Mtn#2026SSD",
            help="Temporary password for Weshiwani (Senior Site Engineer).",
        )
        parser.add_argument("--staff-no", default="MTN-SSD-SSE-001")
        parser.add_argument(
            "--force-change",
            action="store_true",
            help="Require password change on first login.",
        )

    @transaction.atomic
    def handle(self, *args, **opts):
        from buildwatch.models import Country, InfraProject

        User = get_user_model()

        # 1) Country
        country, c_created = Country.objects.get_or_create(
            code="SS",
            defaults={
                "name": "South Sudan",
                "currency_code": "SSP",
                "currency_symbol": "SSP",
                "procurement_law": "Public Procurement Act (South Sudan)",
                "regulator_name": "National Communications Authority / MoICT",
                "is_active": True,
            },
        )
        self.stdout.write(self.style.SUCCESS(
            f"{'Created' if c_created else 'Found'} country {country.code}: {country.name}"
        ))

        # 2) Sponsor organisation (project owner - conceptualization)
        sponsor, s_created = Organization.objects.get_or_create(
            org_code=SPONSOR_CODE,
            defaults={
                "name": SPONSOR_NAME,
                "short_name": SPONSOR_SHORT,
                "contractor_type": Organization.CONTRACTOR_TELECOM,
                "organization_type": "PRIVATE",
                "registration_status": Organization.STATUS_ACTIVE,
                "registered_address": ORG_ADDRESS,
                "contact_address": ORG_ADDRESS,
                "phone": "+211-000-000000",
                "email": "projects@mtn.com.ss",
                "document_tagline": "Telecom infrastructure - South Sudan",
                "accounting_officer_name": "W. Eshiwani",
                "accounting_officer_title": "Senior Site Engineer",
                "profile_summary": PROFILE_SPONSOR,
                "website": "https://www.mtn.com",
            },
        )
        if not s_created:
            sponsor.name = SPONSOR_NAME
            sponsor.short_name = SPONSOR_SHORT
            sponsor.organization_type = "PRIVATE"
            sponsor.contractor_type = Organization.CONTRACTOR_TELECOM
            sponsor.registration_status = Organization.STATUS_ACTIVE
            sponsor.registered_address = ORG_ADDRESS
            sponsor.contact_address = ORG_ADDRESS
            sponsor.accounting_officer_name = "W. Eshiwani"
            sponsor.accounting_officer_title = "Senior Site Engineer"
            sponsor.profile_summary = PROFILE_SPONSOR
            sponsor.save()
        self.stdout.write(self.style.SUCCESS(
            f"{'Created' if s_created else 'Updated'} sponsor {SPONSOR_CODE}: {SPONSOR_NAME}"
        ))

        # 3) Main contractor organisation (telecom infrastructure category)
        contractor, t_created = Organization.objects.get_or_create(
            org_code=CONTRACTOR_CODE,
            defaults={
                "name": CONTRACTOR_NAME,
                "short_name": CONTRACTOR_SHORT,
                "contractor_type": Organization.CONTRACTOR_TELECOM,
                "organization_type": "CONTRACTOR",
                "registration_status": Organization.STATUS_ACTIVE,
                "registered_address": ORG_ADDRESS,
                "contact_address": ORG_ADDRESS,
                "phone": "+211-000-000000",
                "email": "delivery@mtn.com.ss",
                "document_tagline": "Telecom infrastructure contractor",
                "accounting_officer_name": "W. Eshiwani",
                "accounting_officer_title": "Senior Site Engineer",
                "profile_summary": PROFILE_CONTRACTOR,
                "website": "https://www.mtn.com",
            },
        )
        if not t_created:
            contractor.name = CONTRACTOR_NAME
            contractor.short_name = CONTRACTOR_SHORT
            contractor.organization_type = "CONTRACTOR"
            contractor.contractor_type = Organization.CONTRACTOR_TELECOM
            contractor.registration_status = Organization.STATUS_ACTIVE
            contractor.registered_address = ORG_ADDRESS
            contractor.contact_address = ORG_ADDRESS
            contractor.accounting_officer_name = "W. Eshiwani"
            contractor.accounting_officer_title = "Senior Site Engineer"
            contractor.profile_summary = PROFILE_CONTRACTOR
            contractor.save()
        self.stdout.write(self.style.SUCCESS(
            f"{'Created' if t_created else 'Updated'} contractor {CONTRACTOR_CODE} "
            f"(Telecom infrastructure)"
        ))

        # 4) Conceptualization project (sponsor-owned)
        task, task_created = ProjectTask.objects.get_or_create(
            project_id=PROJECT_ID,
            defaults={"description": PROJECT_TITLE},
        )
        if not task_created:
            task.description = PROJECT_TITLE
            task.save(update_fields=["description"])

        project, p_created = InfraProject.objects.get_or_create(
            task=task,
            defaults={
                "owner_org": sponsor,
                "country": country,
                "sector": "ICT",
                "project_type": "PRIVATE",
                "county": "Central Equatoria / Juba",
                "is_active": True,
            },
        )
        if not p_created:
            project.owner_org = sponsor
            project.country = country
            project.sector = "ICT"
            project.project_type = "PRIVATE"
            project.county = "Central Equatoria / Juba"
            project.is_active = True
            project.save()
        self.stdout.write(self.style.SUCCESS(
            f"{'Created' if p_created else 'Updated'} project {PROJECT_ID} "
            f"(ICT / conceptualization - no tender yet)"
        ))

        # 5) Senior Site Engineer login on contractor org
        category, _ = UserCategory.objects.get_or_create(
            code=SENIOR_SITE_MANAGER,
            defaults={
                "description": "Senior Site Manager / Senior Site Engineer",
                "rank": 30,
            },
        )

        username = opts["username"].strip()
        email = opts["email"].strip()
        password = opts["password"]
        staff_no = opts["staff_no"].strip()

        user = User.objects.filter(username__iexact=username).first()
        if user is None:
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                first_name="W.",
                last_name="Eshiwani",
            )
        else:
            user.set_password(password)
            user.email = email
            user.first_name = "W."
            user.last_name = "Eshiwani"
            user.save()

        ua = UserAccount.objects.filter(user=user).first()
        if ua is None:
            ua = UserAccount.objects.filter(staff_no=staff_no).first()
        if ua is None:
            ua = UserAccount(staff_no=staff_no)
        ua.user = user
        ua.first_name = "W."
        ua.last_name = "Eshiwani"
        ua.designation = "Senior Site Engineer"
        ua.contact_address = ORG_ADDRESS
        ua.phone = "+211-000-000000"
        ua.email = email
        ua.access_level = category
        ua.organization = sponsor
        ua.buildwatch_role = "ENGINEER"
        ua.registration_pending_review = False
        ua.must_change_password = bool(opts["force_change"])
        ua.save()

        note = (
            "must change on first login"
            if opts["force_change"]
            else "directly usable, no forced change"
        )
        self.stdout.write(self.style.SUCCESS(
            f"Registered Senior Site Engineer: username='{username}' "
            f"password='{password}' on sponsor org {SPONSOR_CODE} ({note})."
        ))
        self.stdout.write(
            "Sponsor workspace: org MTNSS (PRIVATE) | Contractor: MTNTEL (TELECOM)\n"
            f"Project: {PROJECT_ID} - conceptualization\n"
            "Login as weshiwani -> Main Dashboard / Project Concept\n"
            "Inception: /buildwatch/inception/?profile=ict.telecom_fibre\n"
            "Home: telecom category available under Register as a contractor"
        )
