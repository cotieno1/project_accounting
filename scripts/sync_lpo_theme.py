from pathlib import Path
ROOT = Path(r"C:\project_accounting\templates\includes")

letterhead = """<div class="header" style="text-align:center;border-bottom:3px double #1e3a8a;padding-bottom:14px;margin-bottom:18px;">
    <h1 style="margin:0;font-size:22px;font-weight:bold;letter-spacing:2px;text-transform:uppercase;color:#1e3a8a;">{{ org_name|default:"Client Organization" }}</h1>
    {% if org_contact_address %}<p class="sub" style="margin:6px 0 0;font-size:12px;color:#475569;">{{ org_contact_address|linebreaksbr }}</p>{% endif %}
    {% if org_phone or org_email %}<p style="margin:4px 0 0;font-size:11px;color:#64748b;">{% if org_phone %}Tel: {{ org_phone }}{% endif %}{% if org_phone and org_email %} &bull; {% endif %}{% if org_email %}{{ org_email }}{% endif %}</p>{% endif %}
    {% if doc_subtitle %}<p class="sub" style="margin:8px 0 0;font-size:12px;font-weight:bold;color:#334155;text-transform:uppercase;">{{ doc_subtitle }}</p>{% endif %}
</div>
"""
(ROOT / "pioneer_letterhead_block.html").write_text(letterhead, encoding="utf-8")

toolbar_css = """
    body.pioneer-doc-print { margin: 0; padding: 0; background: #fff; font-family: \"Segoe UI\", Calibri, Arial, sans-serif; font-size: 10pt; color: #1a1a2e; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
    .screen-toolbar { padding: 16px 20px; background: #ecfdf5; border-bottom: 1px solid #a7f3d0; display: flex; gap: 12px; flex-wrap: wrap; justify-content: flex-end; align-items: center; }
    .screen-toolbar button, .screen-toolbar a { padding: 10px 18px; font-size: 13px; border-radius: 8px; font-weight: 600; font-family: inherit; cursor: pointer; text-decoration: none; border: none; }
    .screen-toolbar button { background: #1e3a8a; color: #fff; }
    .screen-toolbar a { background: #059669; color: #fff; }
    .screen-toolbar a.toolbar-muted { background: #f1f5f9; color: #475569; border: 1px solid #cbd5e1; }
    .lpo-sheet { page-break-after: always; }
    .lpo-sheet:last-of-type { page-break-after: avoid; }
    .memo-body p { margin: 0 0 14px; text-align: justify; font-size: 9.5pt; color: #475569; line-height: 1.5; }
    @media print { .no-print, .screen-toolbar { display: none !important; } * { -webkit-print-color-adjust: exact !important; print-color-adjust: exact !important; } }
"""
styles_path = ROOT.parent / "lpo" / "styles.html"
base = styles_path.read_text(encoding="utf-8")
if "screen-toolbar" not in base:
    base = base.replace("</style>", toolbar_css + "\n</style>")
    styles_path.write_text(base, encoding="utf-8")

doc_styles = """{% include "lpo/styles.html" %}
"""
(ROOT / "lpo_document_styles.html").write_text(doc_styles, encoding="utf-8")
print("done")
