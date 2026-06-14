from pathlib import Path
p = Path(r"C:\project_accounting\templates\lpo\styles.html")
p.write_text("""<style>
    @page { size: A4; margin: 10mm; }
    body.lpo-pdf-body {
        margin: 0; padding: 0; background-color: #ffffff;
        font-family: \"Segoe UI\", Calibri, Arial, sans-serif;
        font-size: 10pt; color: #1a1a2e;
    }
    {% if for_pdf %}
    .lpo-paper { max-width: 190mm; margin: 0 auto; padding: 6mm 8mm; background-color: #ffffff; }
    {% else %}
    .lpo-paper { max-width: 210mm; margin: 0 auto; padding: 32px 40px; background-color: #ffffff; }
    {% endif %}
    .doc { max-width: 210mm; margin: 0 auto; font-family: \"Segoe UI\", Calibri, Arial, sans-serif; font-size: 10pt; color: #1a1a2e; line-height: 1.45; }
    .brand-bar { height: 6px; background-color: #1e3a8a; margin-bottom: 18px; }
    .meta-table, .parties, .lines, .signatures { width: 100%; border-collapse: collapse; margin-bottom: 18px; }
    .meta-table th, .lines thead th { background-color: #f1f5f9; color: #475569; font-weight: bold; text-transform: uppercase; font-size: 8pt; padding: 8px 10px; border: 1px solid #cbd5e1; }
    .meta-table td, .lines tbody td, .lines tfoot td { padding: 8px; border: 1px solid #cbd5e1; font-size: 9.5pt; }
    .meta-table .lpo-no { color: #b91c1c; font-weight: bold; }
    .parties th { background-color: #1e3a8a; color: #ffffff; text-align: left; padding: 8px 12px; font-size: 8.5pt; text-transform: uppercase; }
    .parties td { padding: 12px; border: 1px solid #cbd5e1; vertical-align: top; }
    .parties .party-name { font-weight: bold; font-size: 10.5pt; text-transform: uppercase; margin-bottom: 8px; }
    .parties .muted { color: #475569; margin: 3px 0; }
    .lines thead th.num, .lines tbody td.num, .lines tfoot td.num { text-align: right; }
    .lines thead th.center, .lines tbody td.center { text-align: center; }
    .lines tbody tr.zebra { background-color: #f8fafc; }
    .lines tfoot td { font-weight: bold; background-color: #f1f5f9; }
    .lines tfoot .grand-label { text-align: right; text-transform: uppercase; }
    .lines tfoot .grand-value { text-align: right; font-size: 11pt; color: #1e3a8a; font-weight: bold; }
    .terms { border: 1px solid #cbd5e1; background-color: #f8fafc; padding: 12px 14px; margin-bottom: 28px; font-size: 8.5pt; color: #475569; }
    .terms strong { display: block; color: #1e3a8a; text-transform: uppercase; font-size: 8pt; margin-bottom: 6px; }
    .signatures td { width: 45%; text-align: center; padding-top: 40px; vertical-align: bottom; }
    .signatures .line { border-top: 1px solid #1e3a8a; padding-top: 8px; font-size: 8.5pt; font-weight: bold; text-transform: uppercase; }
    .signatures .hint { font-size: 8pt; color: #64748b; margin-top: 4px; }
    .footer-note { margin-top: 24px; text-align: center; font-size: 7.5pt; color: #94a3b8; }
</style>
""", encoding="utf-8")
print("ok", b"\\x00" in p.read_bytes())
