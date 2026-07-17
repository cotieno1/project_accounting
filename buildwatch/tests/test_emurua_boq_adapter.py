"""Emurua AHP PDF adapter scopes priced SMM lines into bid packages."""

from pathlib import Path

from django.test import SimpleTestCase

from buildwatch.boq_ingest.adapters.emurua_ahp_pdf import (
    EmuruaAhpPdfAdapter,
    parse_emurua_text,
)
from buildwatch.boq_ingest.registry import detect_adapter

FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "boq_ingest"
    / "fixtures"
    / "emurua_ahp_sample_extract.txt"
)


class EmuruaAhpAdapterTests(SimpleTestCase):
    def test_sample_extract_yields_priced_lines(self):
        text = FIXTURE.read_text(encoding="utf-8")
        doc = parse_emurua_text(text, source_name=FIXTURE.name)
        self.assertGreater(doc.line_count, 5)
        self.assertGreater(len(doc.categories), 0)
        self.assertEqual(doc.adapter_id, "emurua_ahp_pdf")
        # Walling / Block A style packages should appear
        codes = {c.code for c in doc.categories}
        self.assertTrue(any(c.startswith("BA-") for c in codes))
        paged = [ln for c in doc.categories for ln in c.lines if ln.source_page]
        self.assertGreater(len(paged), 0)
        self.assertTrue(all(isinstance(ln.source_page, int) and ln.source_page >= 1 for ln in paged))

    def test_detect_prefers_emurua_over_isiolo(self):
        adapter, score = detect_adapter(FIXTURE, text_sample=FIXTURE.read_text(encoding="utf-8")[:4000])
        self.assertEqual(adapter.id, "emurua_ahp_pdf")
        self.assertGreater(score, 0.3)
        self.assertIsInstance(adapter, EmuruaAhpPdfAdapter)
