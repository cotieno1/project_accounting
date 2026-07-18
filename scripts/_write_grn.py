from pathlib import Path
CONTENT = """<!DOCTYPE html>
<html lang=\"en\">
<head>
<meta charset=\"UTF-8\">
<title>GRN {{ grn.grn_no }}</title>
<style>
body{font-family:'Times New Roman',serif;color:#000;margin:0;line-height:1.55;font-size:14px;background:#fff}
.grn-sheet{padding:36px 44px;background:#fff;page-break-after:always;box-sizing:border-box}
.grn-sheet:last-of-type{page-break-after:avoid}
.pioneer-letterhead{text-align:center;border-bottom:3px double #000;padding-bottom:14px;margin-bottom:28px}
.pioneer-letterhead .brand{margin:0;font-size:26px;font-weight:bold;letter-spacing:3px;text-transform:uppercase}
.pioneer-letterhead .division{margin:6px 0 0 0;font-size:13px;font-weight:bold;color:#334155;text-transform:uppercase;letter-spacing:1px}
.pioneer-letterhead .doc-type{margin:8px 0 0 0;font-size:12px;color:#475569;text-transform:uppercase}
.memo-block{display:grid;grid-template-columns:150px 1fr;gap:4px 0;margin-bottom:22px;font-size:14px}
.memo-block strong{text-transform:uppercase}
p{margin:0 0 14px 0}
table{width:100%;border-collapse:collapse;margin:18px 0 24px 0;font-size:13px}
th,td{border:1px solid #000;padding:9px 10px;text-align:left;vertical-align:top}
th{background:#f0f0f0;text-transform:uppercase;font-size:11px}
.num{text-align:right}
.signatures{display:grid;grid-template-columns:1fr 1fr;gap:48px;margin-top:42px;page-break-inside:avoid}
.sign-line{border-top:1px solid #000;margin-top:48px;padding-top:6px;font-weight:bold}
.sign-role{font-size:12px;color:#333;margin-top:4px}
.status-banner{border:2px solid #000;padding:12px 16px;margin:18px 0;font-weight:bold;text-transform:uppercase;text-align:center}
.status-full{background:#f5f5f5}.status-partial{background:#fff8e6}
.screen-toolbar{padding:16px 24px;background:#0f172a;border-bottom:1px solid #334155;display:flex;gap:12px;flex-wrap:wrap;justify-content:flex-end}
.screen-toolbar button,.screen-toolbar a{padding:10px 18px;font-size:13px;cursor:pointer;text-decoration:none;border:1px solid #334155;border-radius:6px;font-weight:600}
.screen-toolbar button{background:#10b981;color:#fff;border-color:#10b981}
.screen-toolbar a{background:#1e293b;color:#f1f5f9}
.screen-toolbar a.primary{background:#2563eb;border-color:#2563eb;color:#fff}
@media print{@page{margin:18mm}.screen-toolbar{display:none!important}body{margin:0}}
</style>
</head>
<body>
<div class=\"screen-toolbar\">
<button type=\"button\" onclick=\"window.print()\">Print GRN and Letter</button>
<a href=\"{{ lpo_list_url }}\" class=\"primary\">Back to LPO Listing</a>
<a href=\"/bid-evaluation/?task_id={{ task.project_id }}\">Bid Evaluation</a>
</div>
<div class=\"grn-sheet\">
<div class=\"pioneer-letterhead\">
<h1 class=\"brand\">Pioneer Operations Command</h1>
<p class=\"division\">Procurement and Logistics Division</p>
<p class=\"doc-type\">Delivery Acknowledgement Letter</p>
</div>
<div class=\"memo-block\">
<strong>Date:</strong><div>{{ receipt_date_display }}</div>
<strong>To:</strong><div>{% if supplier %}{{ supplier.description }}{% else %}Supplier{% endif %}</div>
<strong>Attention:</strong><div>{{ supplier_rep }}</div>
<strong>Re:</strong><div>GRN {{ grn.grn_no }} / LPO {{ lpo.lpo_no }} / Task {{ task.project_id }}</div>
<strong>Invoice:</strong><div>{{ grn.invoice_ref|default:\"—\" }}</div>
</div>
{% if is_full_delivery %}
<div class=\"status-banner status-full\">Complete / Full Delivery Confirmed</div>
<p>Dear Sir/Madam,</p>
<p>We formally acknowledge and thank you for the <strong>complete delivery</strong> against LPO <strong>{{ lpo.lpo_no }}</strong> for task <strong>{{ task.project_id }} — {{ task.description }}</strong>.</p>
<p>All ordered line items have been received in full. Please retain the attached signed GRN for your records.</p>
<p>Thank you for your continued partnership.</p>
{% else %}
<div class=\"status-banner status-partial\">Partial Delivery — Balance Outstanding</div>
<p>Dear Sir/Madam,</p>
<p>We acknowledge a <strong>partial delivery</strong> against LPO <strong>{{ lpo.lpo_no }}</strong> (GRN <strong>{{ grn.grn_no }}</strong>).</p>
<table><thead><tr><th>RFQ No</th><th>Description</th><th>UOM</th><th class=\"num\">Ordered</th><th class=\"num\">Received</th><th class=\"num\">Outstanding</th></tr></thead>
<tbody>{% for line in outstanding_lines %}<tr><td>{{ line.rfq_no }}</td><td>{{ line.description }}</td><td>{{ line.uom }}</td><td class=\"num\">{{ line.ordered }}</td><td class=\"num\">{{ line.received }}</td><td class=\"num\"><strong>{{ line.outstanding }}</strong></td></tr>{% endfor %}</tbody></table>
<p>Please arrange delivery of the outstanding balance to close LPO {{ lpo.lpo_no }}.</p>
{% endif %}
<div class=\"signatures\">
<div><p><strong>For Pioneer:</strong></p><div class=\"sign-line\">{{ company_rep }}</div><p class=\"sign-role\">Pioneer Representative</p><p>Date: {{ receipt_date_display }}</p></div>
<div><p><strong>For Supplier:</strong></p><div class=\"sign-line\">{{ supplier_rep }}</div><p class=\"sign-role\">Supplier Representative</p><p>Date: ________________________</p></div>
</div>
</div>
<div class=\"grn-sheet\">
<div class=\"pioneer-letterhead\">
<h1 class=\"brand\">Pioneer Operations Command</h1>
<p class=\"division\">Procurement and Logistics Division</p>
<p class=\"doc-type\">Goods Received Note — {{ grn.grn_no }}</p>
</div>
<div class=\"memo-block\">
<strong>GRN No:</strong><div>{{ grn.grn_no }}</div>
<strong>Receipt Date:</strong><div>{{ receipt_date_display }}</div>
<strong>LPO No:</strong><div>{{ lpo.lpo_no }}</div>
<strong>Task ID:</strong><div>{{ task.project_id }}</div>
<strong>Description:</strong><div>{{ task.description }}</div>
<strong>Supplier:</strong><div>{% if supplier %}{{ supplier.description }} ({{ supplier.supplier_id }}){% else %}—{% endif %}</div>
<strong>Invoice:</strong><div>{{ grn.invoice_ref|default:\"—\" }}</div>
<strong>Delivery Note:</strong><div>{{ grn.delivery_note_ref|default:\"—\" }}</div>
<strong>Status:</strong><div>{% if is_full_delivery %}FULL / COMPLETE{% else %}PARTIAL{% endif %}</div>
</div>
<table><thead><tr><th>#</th><th>RFQ No</th><th>Description</th><th>UOM</th><th class=\"num\">LPO Qty</th><th class=\"num\">This Receipt</th><th class=\"num\">Cumulative</th><th class=\"num\">Outstanding</th></tr></thead>
<tbody>{% for line in receipt_lines %}<tr><td>{{ forloop.counter }}</td><td>{{ line.rfq_no }}</td><td>{{ line.description }}</td><td>{{ line.uom }}</td><td class=\"num\">{{ line.ordered }}</td><td class=\"num\"><strong>{{ line.this_receipt }}</strong></td><td class=\"num\">{{ line.cumulative_received }}</td><td class=\"num\">{% if line.outstanding > 0 %}{{ line.outstanding }}{% else %}—{% endif %}</td></tr>{% endfor %}</tbody></table>
<div class=\"signatures\">
<div><p><strong>Received for Pioneer:</strong></p><div class=\"sign-line\">{{ company_rep }}</div><p>Signature: ________________________</p><p>Date: {{ receipt_date_display }}</p></div>
<div><p><strong>Delivered for Supplier:</strong></p><div class=\"sign-line\">{{ supplier_rep }}</div><p>Signature: ________________________</p><p>Date: ________________________</p></div>
</div>
</div>
<script>window.addEventListener('load',function(){setTimeout(function(){window.print()},500)})</script>
</body></html>"""
Path('templates/grn_print_template.html').write_text(CONTENT, encoding='utf-8')
print('written')
