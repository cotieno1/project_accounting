"""Generate compliance / sign-off checkpoints for a tender from its preambles."""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from buildwatch.compliance import generate_checkpoints_for_tender
from buildwatch.models import TenderListing


class Command(BaseCommand):
    help = "Generate compliance checkpoints (hold points, certificates, site readiness) for a tender."

    def add_arguments(self, parser):
        parser.add_argument("--ref", default="", help="EvaluationEvent ref, e.g. ED-AHP/001/2025-2026")
        parser.add_argument("--listing", type=int, default=0, help="TenderListing pk")
        parser.add_argument("--replace", action="store_true",
                            help="Rebuild un-started checkpoints (keeps ones with sign-off progress).")

    def handle(self, *args, **opts):
        ref = (opts.get("ref") or "").strip()
        pk = int(opts.get("listing") or 0)
        if pk:
            listing = TenderListing.objects.filter(pk=pk).first()
        elif ref:
            listing = TenderListing.objects.filter(event__ref=ref).first()
        else:
            raise CommandError("Pass --ref or --listing")
        if listing is None:
            raise CommandError("Tender not found")

        created = generate_checkpoints_for_tender(listing, replace=bool(opts.get("replace")))
        total = listing.checkpoints.count()
        self.stdout.write(self.style.SUCCESS(
            "Checkpoints created: %d (total now %d) for %s"
            % (created, total, listing.event.ref)
        ))
