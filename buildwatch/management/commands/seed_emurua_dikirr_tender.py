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
                "name": (
                    "State Department for Housing and Urban Development "
                    "(Ministry of Lands, Public Works, Housing and Urban Development)"
                ),
                "short_name": "Housing & Urban Dev.",
                "contractor_type": Organization.CONTRACTOR_ROADS,
                "organization_type": "GOV_NATIONAL",
                "registration_status": Organization.STATUS_ACTIVE,
                "contact_address": "P.O Box 30119-00100 Nairobi, Kenya",
                "phone": "+254-020-2713833",
                "document_tagline": "Affordable Housing Programme",
            },
        )
        if created_emp:
            self.stdout.write(self.style.SUCCESS(f"  + Employer org {EMPLOYER_CODE}"))
        elif not (employer.organization_type or "").strip():
            employer.organization_type = "GOV_NATIONAL"
            employer.save(update_fields=["organization_type"])

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
                created_by=ua,
                boq_input_mode=TenderListing.BOQ_PDF_AUTO,
            )
            self.stdout.write(self.style.SUCCESS("  + TenderListing created"))
        else:
            listing.summary = summary
            listing.country = ke
            listing.county_region = "Narok County"
            listing.tender_type = TenderListing.WORKS
            listing.visibility = TenderListing.PUBLIC
            listing.funding_source = TenderListing.GOV
            listing.boq_input_mode = TenderListing.BOQ_PDF_AUTO
            listing.save()

        with pdf_path.open("rb") as fh:
            listing.boq_document.save(
                "emurua_dikirr_ahp_priced_boq.pdf",
                File(fh),
                save=True,
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
