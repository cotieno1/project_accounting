"""Regression tests for MRO PDF layout (xhtml2pdf-safe tables)."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase

from accounts.misc_doc_pdf import build_pdf_bytes


def _sample_mro_context():
    task = SimpleNamespace(
        project_id="PDF-MRO-TASK-001",
        description="PDF layout regression task",
    )
    mpo = SimpleNamespace(mpo_number="MPO-PDF-001")
    item = SimpleNamespace(
        description="Cement bags",
        uom="bags",
        qty=10,
        unit_price=8,
        total=80,
    )
    mro = SimpleNamespace(
        id=uuid4(),
        mro_number="MRO-PDF-001",
        updated_at=datetime(2026, 6, 12),
        messenger_name="Officer PDF",
        authorized_by=None,
        total_amount=80,
    )
    mro.get_funding_status_display = lambda: "Locked"
    budget = SimpleNamespace(
        material_total_cost=80,
        labour_burden=0,
        misc_reserve=0,
        total_authorized_budget=80,
    )
    return {
        "mro": mro,
        "mpo": mpo,
        "active_task": task,
        "items": [item],
        "budget": budget,
        "currency_symbol": "US$",
        "org_name": "Pioneer Test Org",
        "for_pdf": True,
    }


class MroPdfLayoutTests(SimpleTestCase):
    def test_pdf_html_uses_explicit_column_widths(self):
        html = render_to_string("print_mro.html", _sample_mro_context())
        self.assertNotIn("<colgroup>", html)
        self.assertIn('width="5%"', html)
        self.assertIn('width="38%"', html)
        self.assertIn('cellspacing="0"', html)

    def test_pdf_bytes_generate_without_error(self):
        ctx = _sample_mro_context()
        ctx.pop("for_pdf", None)
        pdf = build_pdf_bytes("print_mro.html", ctx)
        self.assertGreater(len(pdf), 1000)
        self.assertTrue(pdf.startswith(b"%PDF"))