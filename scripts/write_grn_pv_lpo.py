from pathlib import Path

styles = Path("templates/lpo/styles.html")
s = styles.read_text(encoding="utf-8")
extra = """
    .status-full { background-color: #ecfdf5; border: 2px solid #059669; color: #065f46; padding: 12px 16px; margin: 16px 0; font-weight: bold; text-align: center; text-transform: uppercase; font-size: 9pt; }
    .status-partial { background-color: #fffbeb; border: 2px solid #f59e0b; color: #92400e; padding: 12px 16px; margin: 16px 0; font-weight: bold; text-align: center; text-transform: uppercase; font-size: 9pt; }
"""
if ".status-full" not in s:
    s = s.replace("@media print", extra + "\n    @media print")
    styles.write_text(s, encoding="utf-8")

grn = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>GRN {{ grn.grn_no }}</title>
{% include "includes/lpo_document_styles.html" %}
</head>
<body class="pioneer-doc-print">
<div class="screen-toolbar no-print">
<button type="button" onclick="window.print()">Print GRN and Letter</button>
<a href="{{ lpo_list_url }}">Back to LPO Listing</a>
<a href="/bid-evaluation/?task_id={{ task.project_id }}" class="toolbar-muted">Bid Evaluation</a>
</div>
<div class="lpo-paper lpo-sheet"><div class="doc">
<div class="brand-bar"></div>
{% include "includes/pioneer_letterhead_block.html" with doc_subtitle="Delivery Acknowledgement Letter" %}
<table class="meta-table">
<tr><th>Document</th><th>GRN / LPO</th><th>Date</th></tr>
<tr><td>Delivery Acknowledgement</td><td><span class="lpo-no">{{ grn.grn_no }}</span> / {{ lpo.lpo_no }}</td><td>{{ receipt_date_display }}</td></tr>
</table>
<table class="parties">
<tr><th>To — Supplier</th><th>Re — Project</th></tr>
<tr>
<td><div class="party-name">{% if supplier %}{{ supplier.description }}{% else %}Supplier{% endif %}</div><div class="muted">Attn: {{ supplier_rep }}</div></td>
<td><div class="party-name">Task {{ task.project_id }}</div><div class="muted">{{ task.description }}</div><div class="muted">Invoice: {{ grn.invoice_ref|default:"—" }}</div></td>
</tr>
</table>
{% if is_full_delivery %}<div class="status-full">Complete / Full Delivery Confirmed</div>
<div class="terms"><strong>Letter</strong><div class="memo-body"><p>Dear Sir/Madam,</p><p>We formally acknowledge the <strong>complete delivery</strong> against LPO <strong>{{ lpo.lpo_no }}</strong> for task <strong>{{ task.project_id }} — {{ task.description }}</strong>.</p><p>All ordered line items have been received in full. Please retain the attached signed GRN.</p><p>Thank you for your continued partnership.</p></div></div>
{% else %}<div class="status-partial">Partial Delivery — Balance Outstanding</div>
<div class="terms"><strong>Letter</strong><div class="memo-body"><p>Dear Sir/Madam,</p><p>We acknowledge a <strong>partial delivery</strong> against LPO <strong>{{ lpo.lpo_no }}</strong> (GRN <strong>{{ grn.grn_no }}</strong>).</p></div></div>
<table class="lines"><thead><tr><th>RFQ</th><th>Description</th><th>UOM</th><th class="num">Ordered</th><th class="num">Received</th><th class="num">Outstanding</th></tr></thead>
<tbody>{% for line in outstanding_lines %}<tr{% if forloop.counter|divisibleby:2 %} class="zebra"{% endif %}><td>{{ line.rfq_no }}</td><td>{{ line.description }}</td><td class="center">{{ line.uom }}</td><td class="num">{{ line.ordered }}</td><td class="num">{{ line.received }}</td><td class="num"><strong>{{ line.outstanding }}</strong></td></tr>{% endfor %}</tbody></table>
{% endif %}
<table class="signatures"><tr>
<td><div class="line">{{ company_rep }}</div><div class="hint">For {{ org_short_name|default:org_name }}</div></td>
<td style="width:10%"></td>
<td><div class="line">{{ supplier_rep }}</div><div class="hint">Supplier Representative</div></td>
</tr></table>
<p class="footer-note">Letter — {{ grn.grn_no }} — {{ receipt_date_display }}</p>
</div></div>

<div class="lpo-paper lpo-sheet"><div class="doc">
<div class="brand-bar"></div>
{% include "includes/pioneer_letterhead_block.html" with doc_subtitle="Goods Received Note" %}
<table class="meta-table">
<tr><th>Document</th><th>GRN Number</th><th>Receipt date</th></tr>
<tr><td>Goods Received Note</td><td class="lpo-no">{{ grn.grn_no }}</td><td>{{ receipt_date_display }}</td></tr>
</table>
<table class="parties">
<tr><th>Supplier</th><th>Project / LPO</th></tr>
<tr>
<td><div class="party-name">{% if supplier %}{{ supplier.description }}{% else %}—{% endif %}</div><div class="muted">ID: {% if supplier %}{{ supplier.supplier_id }}{% else %}—{% endif %}</div><div class="muted">Delivery note: {{ grn.delivery_note_ref|default:"—" }}</div></td>
<td><div class="party-name">Task {{ task.project_id }}</div><div class="muted">{{ task.description }}</div><div class="muted">LPO: {{ lpo.lpo_no }} · Invoice: {{ grn.invoice_ref|default:"—" }}</div><div class="muted">Status: {% if is_full_delivery %}FULL{% else %}PARTIAL{% endif %}</div></td>
</tr>
</table>
<table class="lines">
<thead><tr><th class="center">#</th><th>RFQ</th><th>Description</th><th class="center">UOM</th><th class="num">LPO Qty</th><th class="num">This rcpt</th><th class="num">Cumulative</th><th class="num">Outstanding</th></tr></thead>
<tbody>{% for line in receipt_lines %}<tr{% if forloop.counter|divisibleby:2 %} class="zebra"{% endif %}><td class="center">{{ forloop.counter }}</td><td>{{ line.rfq_no }}</td><td>{{ line.description }}</td><td class="center">{{ line.uom }}</td><td class="num">{{ line.ordered }}</td><td class="num"><strong>{{ line.this_receipt }}</strong></td><td class="num">{{ line.cumulative_received }}</td><td class="num">{% if line.outstanding > 0 %}{{ line.outstanding }}{% else %}—{% endif %}</td></tr>{% endfor %}</tbody>
</table>
<table class="signatures"><tr>
<td><div class="line">{{ company_rep }}</div><div class="hint">Received for {{ org_short_name|default:org_name }}</div></td>
<td style="width:10%"></td>
<td><div class="line">{{ supplier_rep }}</div><div class="hint">Delivered for Supplier</div></td>
</tr></table>
<p class="footer-note">GRN — {{ grn.grn_no }} — {{ receipt_date_display }}</p>
</div></div>
<script>window.addEventListener('load',function(){setTimeout(function(){window.print()},500)});</script>
</body></html>
"""
Path("templates/grn_print_template.html").write_text(grn, encoding="utf-8")

pv = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Payment Voucher {{ voucher.pay_order_no }}</title>
{% include "includes/lpo_document_styles.html" %}
</head>
<body class="pioneer-doc-print">
<div class="screen-toolbar no-print">
<button type="button" onclick="window.print()">Print Voucher</button>
<a href="{{ grn_list_url }}">Back to GRN Listing</a>
</div>
<div class="lpo-paper"><div class="doc">
<div class="brand-bar"></div>
{% include "includes/pioneer_letterhead_block.html" with doc_subtitle="Accounts Payable — Payment Input Voucher" %}
<table class="meta-table">
<tr><th>Document</th><th>Voucher No.</th><th>Date</th></tr>
<tr><td>Payment Input Voucher</td><td class="lpo-no">{{ voucher.pay_order_no }}</td><td>{{ voucher.created_at|date:"F d, Y" }}</td></tr>
</table>
<table class="parties">
<tr><th>Payee — Supplier</th><th>Project / References</th></tr>
<tr>
<td><div class="party-name">{% if supplier %}{{ supplier.description }}{% endif %}</div><div class="muted">Method: {{ voucher.get_payment_method_display }}</div><div class="muted">Bank: {{ voucher.source_bank.description }} ({{ voucher.source_bank.account_number }})</div>{% if voucher.payment_method == "BANK" %}<div class="muted">Transfer ref: {{ voucher.transfer_reference }}</div>{% elif voucher.payment_method == "CHQ" %}<div class="muted">Cheque: {{ voucher.cheque_number }}</div>{% endif %}</td>
<td><div class="party-name">Task {{ task.project_id }}</div><div class="muted">{{ task.description }}</div><div class="muted">GRN: {{ grn.grn_no }} · LPO: {{ lpo.lpo_no }}</div><div class="muted">Invoice: {{ grn.invoice_ref }}</div></td>
</tr>
</table>
<table class="meta-table">
<tr><th colspan="2">Payment amount (US$)</th></tr>
<tr><td colspan="2" class="lpo-no" style="font-size:12pt;font-family:monospace;">{{ amount|floatformat:2 }}</td></tr>
</table>
<table class="lines">
<thead><tr><th class="center">#</th><th>Description</th><th class="center">UOM</th><th class="num">Qty rcvd</th><th class="num">Unit (US$)</th><th class="num">Line total</th></tr></thead>
<tbody>{% for line in receipt_lines %}<tr{% if forloop.counter|divisibleby:2 %} class="zebra"{% endif %}><td class="center">{{ forloop.counter }}</td><td>{{ line.description }}</td><td class="center">{{ line.uom }}</td><td class="num">{{ line.this_receipt }}</td><td class="num">{{ line.unit_price }}</td><td class="num">{{ line.line_total }}</td></tr>{% endfor %}</tbody>
<tfoot><tr><td colspan="5" class="grand-label">Voucher total (US$)</td><td class="grand-value">{{ amount|floatformat:2 }}</td></tr></tfoot>
</table>
<div class="terms"><strong>Authorization</strong>Authorise payment of <strong>US$ {{ amount|floatformat:2 }}</strong> in settlement of GRN <strong>{{ grn.grn_no }}</strong> against invoice <strong>{{ grn.invoice_ref }}</strong>.{% if voucher.payment_notes %} Notes: {{ voucher.payment_notes }}{% endif %}</div>
<table class="signatures"><tr>
<td><div class="line">{{ voucher.prepared_by_name|default:"________________________" }}</div><div class="hint">Prepared by — Accounts</div></td>
<td style="width:10%"></td>
<td><div class="line">________________________</div><div class="hint">Authorised by — Director / GM</div></td>
</tr></table>
<p class="footer-note">Voucher — {{ voucher.pay_order_no }} — {{ voucher.created_at|date:"Y-m-d" }}</p>
</div></div>
<script>window.addEventListener('load',function(){setTimeout(function(){window.print()},500)});</script>
</body></html>
"""
Path("templates/payment_voucher_print.html").write_text(pv, encoding="utf-8")
print("grn pv done")
