"""Generate LPO PDF using the same templates as the on-screen view."""
import re
from io import BytesIO
from pathlib import Path
from django.conf import settings
from django.template.loader import render_to_string

def _safe_filename(lpo_no):
    return re.sub(r"[^\w\-]", "_", str(lpo_no or "LPO"))[:80]

def _media_root():
    root = getattr(settings, "MEDIA_ROOT", None)
    if root:
        return Path(root)
    return Path(settings.BASE_DIR) / "media"

def lpo_pdf_directory():
    path = _media_root() / "lpo_pdfs"
    path.mkdir(parents=True, exist_ok=True)
    return path

def lpo_pdf_filepath(lpo_no):
    return lpo_pdf_directory() / f"{_safe_filename(lpo_no)}.pdf"

def pdf_exists(lpo_no):
    return lpo_pdf_filepath(lpo_no).exists()

def render_lpo_html(context):
    return render_to_string("procurement_lpo_document.html", context)

def build_pdf_bytes(context):
    context = {**context, "for_pdf": True}
    try:
        from xhtml2pdf import pisa
    except ImportError as exc:
        raise ImportError("PDF export needs xhtml2pdf. Run: pip install xhtml2pdf") from exc
    html = render_lpo_html(context)
    buffer = BytesIO()
    status = pisa.CreatePDF(html, dest=buffer, encoding="utf-8", show_error_as_pdf=False)
    if status.err:
        raise RuntimeError("PDF generation failed.")
    return buffer.getvalue()

def save_lpo_pdf(lpo_no, context):
    path = lpo_pdf_filepath(lpo_no)
    path.write_bytes(build_pdf_bytes(context))
    return path