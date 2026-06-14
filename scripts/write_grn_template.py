from pathlib import Path
CONTENT = """<!DOCTYPE html>
<html lang=\"en\">
<head>
<meta charset=\"UTF-8\">
<title>GRN {{ grn.grn_no }}</title>
<style>
body{font-family:'Times New Roman',serif;color:#000;margin:40px;line-height:1.55;font-size:14px}
.header{text-align:center;border-bottom:2px solid #000;padding-bottom:12px;margin-bottom:28px}
.title{font-size:22px;font-weight:bold;margin:0;text-transform:uppercase}
.subtitle{font-size:13px;margin:6px 0 0 0}
.memo-block{display:grid;grid-template-columns:160px 1fr;gap:4px 0;margin-bottom:22px}
.memo-block strong{text-transform:uppercase}
p{margin:0 0 14px 0}
table{width:100%;border-collapse:collapse;margin:18px 0 26px 0;font-size:13px}
th,td{border:1px solid #000;padding:9px 10px;text-align:left;vertical-align:top}
th{background:#f0f0f0;text-transform:uppercase;font-size:11px}
.num{text-align:right}
.signatures{display:grid;grid-template-columns:1fr 1fr;gap:48px;margin-top:42px}
.sign-line{border-top:1px solid #000;margin-top:48px;padding-top:6px;font-weight:bold}
.sign-role{font-size:12px;color:#333;margin-top:4px}
.page-break{page-break-before:always;margin-top:0}
.status-banner{border:2px solid #000;padding:12px 16px;margin:18px 0;font-weight:bold;text-transform:uppercase;text-align:center}
.status-full{background:#f5f5f5}.status-partial{background:#fff8e6}
.toolbar{margin-bottom:24px;display:flex;gap:10px}
.toolbar button,.toolbar a{padding:10px 18px;font-size:13px;cursor:pointer;text-decoration:none;border:1px solid #000;background:#f0f0f0;color:#000}
@media print{@page{margin:18mm}body{margin:0}.toolbar{display:none}}
</style>
</head>
<body>
<div class=\"toolbar\"><button type=\"button\" onclick=\"window.print()\">Print GRN and Letter</button><a href=\"/bid-evaluation/?task_id={{ task.project_id }}\">Back to Bid Evaluation</a></div>
<div class=\"header\"><h1 class=\"title\">Pioneer Operations Command</h1><p class=\"subtitle\">Delivery Acknowledgement Letter</p></div>
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
<p>We acknowledge a <strong>partial delivery</strong> against LPO <strong>{{ lpo.lpo_no }}</strong> (GRN <strong>{{ grn.grn_no }}</strong>). Outstanding quantities:</p>
<table><thead><tr><th>RFQ No</th><th>Description</th><th>UOM</th><th class=\"num\">Ordered</th><th class=\"num\">Received</th><th class=\"num\">Outstanding</th></tr></thead><tbody>{% for line in outstanding_lines %}<tr><td>{{ line.rfq_no }}</td><td>{{ line.description }}</td><td>{{ line.uom }}</td><td class=\"num\">{{ line.ordered }}</td><td class=\"num\">{{ line.received }}</td><td class=\"num\"><strong>{{ line.outstanding }}</strong></td></tr>{% endfor %}</tbody></table>
<p>Please arrange delivery of the outstanding balance to close LPO {{ lpo.lpo_no }}.</p>
{% endif %}
<div class=\"signatures\"><div><p><strong>For Pioneer:</strong></p><div class=\"sign-line\">{{ company_rep }}</div><p class=\"sign-role\">Pioneer Representative</p><p>Date: {{ receipt_date_display }}</p></div><div><p><strong>For Supplier:</strong></p><div class=\"sign-line\">{{ supplier_rep }}</div><p class=\"sign-role\">Supplier Representative</p><p>Date: ________________________</p></div></div>
<div class=\"page-break\"></div>
<div class=\"header\"><h1 class=\"title\">Goods Received Note</h1><p class=\"subtitle\">GRN {{ grn.grn_no }}</p></div>
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
<table><thead><tr><th>#</th><th>RFQ No</th><th>Description</th><th>UOM</th><th class=\"num\">LPO Qty</th><th class=\"num\">This Receipt</th><th class=\"num\">Cumulative</th><th class=\"num\">Outstanding</th></tr></thead><tbody>{% for line in receipt_lines %}<tr><td>{{ forloop.counter }}</td><td>{{ line.rfq_no }}</td><td>{{ line.description }}</td><td>{{ line.uom }}</td><td class=\"num\">{{ line.ordered }}</td><td class=\"num\"><strong>{{ line.this_receipt }}</strong></td><td class=\"num\">{{ line.cumulative_received }}</td><td class=\"num\">{% if line.outstanding > 0 %}{{ line.outstanding }}{% else %}—{% endif %}</td></tr>{% endfor %}</tbody></table>
<div class=\"signatures\"><div><p><strong>Received for Pioneer:</strong></p><div class=\"sign-line\">{{ company_rep }}</div><p>Signature: ________________________</p><p>Date: {{ receipt_date_display }}</p></div><div><p><strong>Delivered for Supplier:</strong></p><div class=\"sign-line\">{{ supplier_rep }}</div><p>Signature: ________________________</p><p>Date: ________________________</p></div></div>
<script>window.addEventListener('load',function(){setTimeout(function(){window.print()},400)})</script>
</body></html>"""
Path('templates/grn_print_template.html').write_text(CONTENT, encoding='utf-8')
print('template ok')
