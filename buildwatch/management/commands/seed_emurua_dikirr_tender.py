# -*- coding: utf-8 -*-
# ============================================================================
# buildwatch/management/commands/seed_emurua_dikirr_tender.py
#
# Publishes Emurua Dikirr Affordable Housing Project BOQ to the tender exchange
# with the same listing UX / bidder actions as SK/004/2025-2026.
#
# Source PDF (preferred order):
#   1) --pdf path
#   2) buildwatch/boq_ingest/fixtures/emurua_dikirr_ahp_priced_boq.pdf
#   3) ~/Downloads/EMURUA DIKIRR AHP PRICED BOQ.pdf
#
# Run: python manage.py seed_emurua_dikirr_tender
# Safe to re-run (updates BOQ file + republishes if already present).
# ============================================================================

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from django.core.files import File
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from accounts.models import Organization, ProjectTask, UserAccount
from buildwatch.models import (
    Country,
    EvaluationEvent,
    InfraProject,
    TenderListing,
)

REF = "ED-AHP/001/2025-2026"
TASK_ID = "ED_AHP_001"
EMPLOYER_CODE = "SDHUD"
EMPLOYER_NAME = (
    "Ministry of Lands, Public Works, Housing and Urban Development - "
    "State Department of Housing and Urban Development"
)
EMPLOYER_OFFICER_NAME = "Eng Charles Korir"
EMPLOYER_OFFICER_TITLE = "Principal Secretary"
EMPLOYER_ADDRESS = (
    "Ministry of Lands, Public Works, Housing and Urban Development\n"
    "State Department of Housing and Urban Development\n"
    "P.O Box 30119-00100\n"
    "NAIROBI, KENYA"
)

WORKS_DESCRIPTION = """DESCRIPTION OF THE WORKS
The construction comprises reinforced concrete foundations, masonry walling, reinforced
concrete beams, columns, staircases and suspended solid slabs, roof construction.
The exterior facade consists of steel casement windows, steel and timber doors, render and
paint finish, clay and stone facing finish to walls.
The interior works includes timber doors and finishes which are generally plaster and paint to
walls, ceramic and non slip ceramic tiles to floors and walls.
External works generally comprise of foul water drainage, storm water drainage, pathway,
dryline area, septic tank, underground water tank.
All mechanical / electrical services and other specialist works associated with the above
works shall be executed by domestic/nominated sub contractors approved by the Engineer."""

CONTRACT_PARTICULARS = """CONTRACT PARTICULARS
B FORM OF CONTRACT
The Contractor will be required to enter into a contract with
the Employer under the Terms and Conditions of Contract as "Standard Tender Document
for Procurement of Works (Building and Associated Civil Engineering Works)" issued by
the Public Procurement Regulatory Authority in February 2021 (updated 2022) and in
association with the latest applicable version of the Public Procurement and Asset Disposal
Act.
The Contractor's attention is called to the appendix of the conditions of Contract and
additions and amendments thereto, which shall be read as incorporated herein and he shall
allow any sums which he considers necessary for the observance of such conditions,
together with sub clauses used in application.
The priority of such documents shall be as stated in the conditions of agreement."""

FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "boq_ingest"
    / "fixtures"
    / "emurua_dikirr_ahp_priced_boq.pdf"
)
DOWNLOADS_CANDIDATES = [
    Path.home() / "Downloads" / "EMURUA DIKIRR AHP PRICED BOQ.pdf",
    Path.home() / "Downloads" / "EMURUA DIKIRR AHP PRICED BOQ (1).pdf",
]


def _resolve_pdf(explicit: str | None) -> Path:
    if explicit:
        path = Path(explicit)
        if not path.exists():
            raise CommandError(f"PDF not found: {path}")
        return path
    if FIXTURE.exists():
        return FIXTURE
    for cand in DOWNLOADS_CANDIDATES:
        if cand.exists():
            return cand
    raise CommandError(
        "Emurua Dikirr PDF not found. Place it at "
        f"{FIXTURE} or pass --pdf /path/to/file.pdf"
    )


class Command(BaseCommand):
    help = "Publish Emurua Dikirr AHP priced BOQ as a new exchange tender"

    def add_arguments(self, parser):
        parser.add_argument(
            "--pdf",
            default="",
            help="Optional absolute path to the BOQ PDF",
        )
        parser.add_argument(
            "--days-open",
            type=int,
            default=45,
            help="Days until closing (default 45)",
        )

    def handle(self, *args, **options):
        pdf_path = _resolve_pdf((options.get("pdf") or "").strip() or None)
        days_open = int(options.get("days_open") or 45)
        self.stdout.write(f"Using PDF: {pdf_path} ({pdf_path.stat().st_size:,} bytes)")

        ke, _ = Country.objects.get_or_create(
            code="KE",
            defaults={
                "name": "Kenya",
                "currency_code": "KES",
                "currency_symbol": "KES",
                "is_active": True,
            },
        )

        employer, created_emp = Organization.objects.get_or_create(
            org_code=EMPLOYER_CODE,
            defaults={
                "name": EMPLOYER_NAME,
                "short_name": "State Dept. of Housing",
                "contractor_type": Organization.CONTRACTOR_ROADS,
                "organization_type": "GOV_NATIONAL",
                "registration_status": Organization.STATUS_ACTIVE,
                "registered_address": EMPLOYER_ADDRESS,
                "contact_address": EMPLOYER_ADDRESS,
                "phone": "+254-020-2713833",
                "document_tagline": "Affordable Housing Programme",
                "accounting_officer_name": EMPLOYER_OFFICER_NAME,
                "accounting_officer_title": EMPLOYER_OFFICER_TITLE,
            },
        )
        if created_emp:
            self.stdout.write(self.style.SUCCESS(f"  + Employer org {EMPLOYER_CODE}"))
        else:
            # Keep the sponsor identity current on re-run.
            employer.name = EMPLOYER_NAME
            employer.short_name = "State Dept. of Housing"
            employer.organization_type = "GOV_NATIONAL"
            employer.registration_status = Organization.STATUS_ACTIVE
            employer.registered_address = EMPLOYER_ADDRESS
            employer.contact_address = EMPLOYER_ADDRESS
            employer.accounting_officer_name = EMPLOYER_OFFICER_NAME
            employer.accounting_officer_title = EMPLOYER_OFFICER_TITLE
            if not (employer.phone or "").strip():
                employer.phone = "+254-020-2713833"
            employer.save(update_fields=[
                "name", "short_name", "organization_type", "registration_status",
                "registered_address", "contact_address", "phone",
                "accounting_officer_name", "accounting_officer_title",
            ])

        task, _ = ProjectTask.objects.get_or_create(
            project_id=TASK_ID,
            defaults={
                "description": (
                    "Proposed Construction of Emurua Dikirr Affordable Housing "
                    "Project in Narok County"
                ),
            },
        )

        project, p_created = InfraProject.objects.get_or_create(
            task=task,
            defaults={
                "owner_org": employer,
                "country": ke,
                "sector": "BUILDINGS",
                "project_type": "GOV",
                "county": "Narok",
                "contract_value": Decimal("0"),
                "is_active": True,
            },
        )
        if not p_created and project.owner_org_id != employer.pk:
            project.owner_org = employer
            project.country = ke
            project.county = "Narok"
            project.sector = "BUILDINGS"
            project.is_active = True
            project.save()

        ua = (
            UserAccount.objects.filter(organization=employer)
            .order_by("id")
            .first()
            or UserAccount.objects.filter(user__is_superuser=True)
            .order_by("id")
            .first()
            or UserAccount.objects.order_by("id").first()
        )
        if ua is None:
            raise CommandError(
                "No UserAccount available to attribute the tender. "
                "Create a platform admin / employer user first."
            )

        now = timezone.now()
        closing = now + timedelta(days=days_open)
        description = (
            "Proposed Construction of Emurua Dikirr Affordable Housing Project "
            "in Narok County - Bills of Quantities"
        )
        summary = (
            "Affordable Housing Programme BOQ for Emurua Dikirr, Narok County. "
            "Issued by the State Department for Housing and Urban Development "
            "(Ministry of Lands, Public Works, Housing and Urban Development). "
            "Register interest to download the priced BOQ PDF and open the bid workspace."
        )

        event = EvaluationEvent.objects.filter(ref=REF).first()
        if event is None:
            event = EvaluationEvent.objects.create(
                project=project,
                context=EvaluationEvent.PROCUREMENT,
                ref=REF,
                description=description,
                issue_date=now.date(),
                closing_date=closing,
                status=EvaluationEvent.STATUS_OPEN,
                min_pass_score=Decimal("70"),
                created_by=ua,
            )
            self.stdout.write(self.style.SUCCESS(f"  + EvaluationEvent {REF}"))
        else:
            event.project = project
            event.description = description
            event.status = EvaluationEvent.STATUS_OPEN
            if event.closing_date < now:
                event.closing_date = closing
            event.save()

        listing = TenderListing.objects.filter(event=event).first()
        if listing is None:
            listing = TenderListing.objects.create(
                event=event,
                tender_type=TenderListing.WORKS,
                visibility=TenderListing.PUBLIC,
                funding_source=TenderListing.GOV,
                country=ke,
                county_region="Narok County",
                currency="KES",
                summary=summary,
                works_description=WORKS_DESCRIPTION,
                contract_particulars=CONTRACT_PARTICULARS,
                created_by=ua,
                boq_input_mode=TenderListing.BOQ_PDF_AUTO,
                mr_checklist="",  # housing BOQ - conditions replace MR pack
            )
            self.stdout.write(self.style.SUCCESS("  + TenderListing created"))
        else:
            listing.summary = summary
            listing.works_description = WORKS_DESCRIPTION
            listing.contract_particulars = CONTRACT_PARTICULARS
            listing.country = ke
            listing.county_region = "Narok County"
            listing.tender_type = TenderListing.WORKS
            listing.visibility = TenderListing.PUBLIC
            listing.funding_source = TenderListing.GOV
            listing.boq_input_mode = TenderListing.BOQ_PDF_AUTO
            listing.mr_checklist = ""
            listing.save()

        # Keep Isiolo electrical checklist scoped to SK/004 only
        TenderListing.objects.filter(event__ref="SK/004/2025-2026").exclude(
            mr_checklist=TenderListing.MR_CHECKLIST_KE_ELECTRICAL_RFQ
        ).update(mr_checklist=TenderListing.MR_CHECKLIST_KE_ELECTRICAL_RFQ)

        with pdf_path.open("rb") as fh:
            listing.boq_document.save(
                "emurua_dikirr_ahp_priced_boq.pdf",
                File(fh),
                save=True,
            )

        # Persist structured packages/lines so the bid workspace is not empty.
        try:
            from buildwatch.boq_ingest.persist import apply_standard_boq
            from buildwatch.boq_ingest.sources import load_pdf_auto_boq

            doc = load_pdf_auto_boq(listing)
            stats = apply_standard_boq(listing, doc)
            listing.boq_input_mode = TenderListing.BOQ_PDF_AUTO
            listing.save(update_fields=["boq_input_mode"])
            self.stdout.write(
                self.style.SUCCESS(
                    "  + BOQ ingest: %s packages, %s lines (%s)"
                    % (stats["categories"], stats["lines"], stats.get("adapter_id"))
                )
            )
        except Exception as exc:
            self.stdout.write(
                self.style.WARNING("  ! BOQ ingest skipped: %s" % exc)
            )

        if not listing.is_published:
            listing.publish(ua)
            self.stdout.write(self.style.SUCCESS("  + Published to exchange"))
        else:
            listing.published_at = listing.published_at or now
            listing.save(update_fields=["published_at", "boq_document"])

        self.stdout.write(
            self.style.SUCCESS(
                f"Emurua Dikirr ready: /tenders/{listing.pk}/  ref={REF}  "
                f"boq={'yes' if listing.boq_document else 'no'}"
            )
        )
