"""Seed the consultant / professional team for the Emurua Dikirr tender.

Lightweight (no BOQ re-ingest) so it can be run on production to populate the
consultant team from the BOQ particulars.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from buildwatch.models import TenderConsultant, TenderListing


class Command(BaseCommand):
    help = "Seed the consultant team (PM/Engineer, Architect, QS, Structural, M&E) for a tender."

    def add_arguments(self, parser):
        parser.add_argument("--ref", default="ED-AHP/001/2025-2026",
                            help="EvaluationEvent ref.")

    def handle(self, *args, **opts):
        ref = (opts.get("ref") or "").strip()
        listing = TenderListing.objects.filter(event__ref=ref).select_related(
            "event", "event__project", "event__project__owner_org").first()
        if listing is None:
            raise CommandError("Tender not found: %s" % ref)

        owner = listing.event.project.owner_org
        addr = "P.O Box 30119 - 00100, NAIROBI, KENYA"
        team = [
            (TenderConsultant.PM_ENGINEER, None,
             "The Engineer (as defined in Condition 1 of the Conditions of Contract)", "",
             "Or such person(s) duly authorised to represent him on behalf of the Government."),
            (TenderConsultant.ARCHITECT, owner, "", addr, ""),
            (TenderConsultant.QS, owner, "", addr, ""),
            (TenderConsultant.STRUCTURAL_CIVIL, owner, "", addr, ""),
            (TenderConsultant.ELECTRICAL_MECHANICAL, owner, "", addr, ""),
        ]
        created = 0
        for i, (role, org_obj, firm, a, note) in enumerate(team):
            _, made = TenderConsultant.objects.update_or_create(
                tender=listing, role=role,
                defaults={"organisation": org_obj, "firm_name": firm, "address": a,
                          "notes": note, "sort_order": (i + 1) * 10})
            created += 1 if made else 0

        self.stdout.write(self.style.SUCCESS(
            "Consultant team set for %s: %d roles (%d new)."
            % (ref, len(team), created)))
