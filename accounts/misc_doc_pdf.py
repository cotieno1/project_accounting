"""Generate misc MRO/RO PDFs from the same HTML templates as the screen view."""
from io import BytesIO
import re

from django.template.loader import render_to_string


def _safe_filename(name):
    return re.sub(r"[^\w\-]", "_", str(name or "document"))[:80]


def build_pdf_bytes(template_name, context):
    """Render template to PDF bytes (A4) via xhtml2pdf."""
    context = {**context, "for_pdf": True}
    try:
        from xhtml2pdf import pisa
    except ImportError as exc:
        raise ImportError(
            "PDF export needs xhtml2pdf. Run: pip install xhtml2pdf"
        ) from exc

    html = render_to_string(template_name, context)
    buffer = BytesIO()
    status = pisa.CreatePDF(
        html, dest=buffer, encoding="utf-8", show_error_as_pdf=False
    )
    if status.err:
        raise RuntimeError("PDF generation failed.")
    return buffer.getvalue()


def pdf_inline_response(pdf_bytes, filename):
    from django.http import HttpResponse

    safe = _safe_filename(filename)
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{safe}.pdf"'
    response["Cache-Control"] = "private, max-age=300"
    return response
