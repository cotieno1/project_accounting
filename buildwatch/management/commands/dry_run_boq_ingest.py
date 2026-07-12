"""Dry-run RFQ/BOQ ingest -> StandardBoq JSON (no TenderBoq DB writes)."""
from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from buildwatch.boq_ingest import detect_adapter, get_adapter, list_adapters


class Command(BaseCommand):
    help = (
        "Parse an RFQ/BOQ file into StandardBoq JSON without writing "
        "TenderBoqPackage/Line or touching the live Isiolo seed."
    )

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True, help="Path to PDF/TXT/…")
        parser.add_argument(
            "--adapter",
            default="auto",
            help="Adapter id or 'auto' (available: %s)" % ", ".join(list_adapters() or ["isiolo_domestic_pdf"]),
        )
        parser.add_argument(
            "--out",
            default="",
            help="Optional output JSON path (default: stdout summary + scripts/_dry_run_*.json)",
        )

    def handle(self, *args, **options):
        path = Path(options["file"]).expanduser().resolve()
        if not path.exists():
            raise CommandError("File not found: %s" % path)

        adapter_id = (options["adapter"] or "auto").strip()
        if adapter_id == "auto":
            adapter, score = detect_adapter(path)
            self.stdout.write("auto-detected %s (confidence %.2f)" % (adapter.id, score))
        else:
            adapter = get_adapter(adapter_id)
            self.stdout.write("using adapter %s" % adapter.id)

        doc = adapter.parse(path)
        payload = doc.to_dict()

        out = options["out"]
        if out:
            out_path = Path(out).expanduser().resolve()
        else:
            out_path = Path("scripts") / ("_dry_run_%s.json" % adapter.id)
            out_path.parent.mkdir(parents=True, exist_ok=True)

        out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

        self.stdout.write(self.style.SUCCESS(
            "OK adapter=%s categories=%d lines=%d warnings=%d -> %s"
            % (
                doc.adapter_id,
                len(doc.categories),
                doc.line_count,
                len(doc.warnings),
                out_path,
            )
        ))
        for cat in doc.categories:
            self.stdout.write(
                "  %s  %3d  %s" % (cat.code, len(cat.lines), cat.title)
            )
        for wmsg in doc.warnings:
            self.stdout.write(self.style.WARNING("  warn: %s" % wmsg))
        self.stdout.write(
            "NOTE: dry-run only — did not modify TenderBoqPackage/Line or seed_isiolo_boq."
        )
