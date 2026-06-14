from pathlib import Path

ro = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>RO {{ ro.ro_no }}</title>
{% include "includes/lpo_document_styles.html" %}
</head>
<body class="pioneer-doc-print">
<div class="screen-toolbar no-print">
<button type="button" onclick="window.print()">Print Requisition Order</button>
</div>
<div class="lpo-paper"><div class="doc">
<div class="brand-bar"></div>
{% include "includes/pioneer_letterhead_block.html" with doc_subtitle="Requisition Order" %}
<table class="meta-table">
<tr><th>Document</th><th>RO Number</th><th>Date</th></tr>
<tr><td>Requisition Order</td><td class="lpo-no">{{ ro.ro_no }}</td><td>{% now "d M Y" %}</td></tr>
</table>
<table class="parties">
<tr><th>To</th><th>From</th></tr>
<tr><td><div class="party-name">General Manager</div></td><td><div class="party-name">Senior Site Engineer</div><div class="muted">{{ org_short_name|default:org_name }}</div></td></tr>
</table>
<table class="lines">
<thead><tr><th>Description</th><th class="num">Qty</th><th class="center">Unit</th></tr></thead>
<tbody>{% for item in ro.items.all %}<tr{% if forloop.counter|divisibleby:2 %} class="zebra"{% endif %}><td>{{ item.tech_spec_summary }}</td><td class="num">{{ item.quantity }}</td><td class="center">{{ item.uom }}</td></tr>{% endfor %}</tbody>
</table>
<table class="signatures"><tr>
<td><div class="line">Senior Site Engineer</div><div class="hint">{{ org_short_name|default:org_name }}</div></td>
<td style="width:10%"></td>
<td><div class="line">General Manager</div><div class="hint">Authorization</div></td>
</tr></table>
<p class="footer-note">RO — {{ ro.ro_no }} — {% now "Y-m-d" %}</p>
</div></div>
<script>window.addEventListener('load',function(){setTimeout(function(){window.print()},400)});</script>
</body></html>
"""
Path("templates/ro_print_template.html").write_text(ro, encoding="utf-8")

# adhoc officer voucher - read rest of file for lines loop
adhoc = Path("templates/adhoc_officer_voucher_print.html").read_text(encoding="utf-8")
# rewrite fully
adhoc_new = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Officer Payment Voucher {{ voucher.voucher_no }}</title>
{% include "includes/lpo_document_styles.html" %}
</head>
<body class="pioneer-doc-print">
<div class="screen-toolbar no-print">
<button type="button" onclick="window.print()">Print Voucher</button>
<a href="{{ ro_list_url }}">Back to RO Listing</a>
</div>
<div class="lpo-paper"><div class="doc">
<div class="brand-bar"></div>
{% include "includes/pioneer_letterhead_block.html" with doc_subtitle="Ad-Hoc Procurement — Officer Payment Voucher" %}
<table class="meta-table">
<tr><th>Document</th><th>Voucher No.</th><th>Date</th></tr>
<tr><td>Officer Payment Voucher</td><td class="lpo-no">{{ voucher.voucher_no }}</td><td>{{ voucher.created_at|date:"F d, Y" }}</td></tr>
</table>
<table class="parties">
<tr><th>Payee — Officer</th><th>Project / RO</th></tr>
<tr>
<td><div class="party-name">{{ voucher.officer_name }}</div><div class="muted">{{ voucher.get_payment_method_display }}{% if voucher.payment_method == "MPESA" %} · {{ voucher.mpesa_reference }}{% endif %}</div></td>
<td><div class="party-name">Task {{ task.project_id }}</div><div class="muted">{{ task.description }}</div><div class="muted">RO: {{ mpo.mpo_number }}</div></td>
</tr>
</table>
<table class="meta-table"><tr><th>Payment amount (US$)</th></tr><tr><td class="lpo-no" style="font-family:monospace;font-size:12pt;">{{ voucher.amount|floatformat:2 }}</td></tr></table>
<div class="terms"><strong>Authorization</strong>Payment to officer <strong>{{ voucher.officer_name }}</strong> for partial purchase against Ad-Hoc RO <strong>{{ mpo.mpo_number }}</strong>. Not an LPO supplier payment.{% if voucher.payment_notes %} {{ voucher.payment_notes }}{% endif %}</div>
<table class="lines">
<thead><tr><th class="center">#</th><th>Description</th><th class="center">UOM</th><th class="num">Qty RO</th><th class="num">Buy</th><th class="num">Balance</th><th class="num">Unit</th><th class="num">Total</th></tr></thead>
<tbody>{% for line in purchase_lines %}<tr{% if forloop.counter|divisibleby:2 %} class="zebra"{% endif %}><td class="center">{{ line.line_no }}</td><td>{{ line.description }}</td><td class="center">{{ line.uom }}</td><td class="num">{{ line.qty_ro }}</td><td class="num">{{ line.qty }}</td><td class="num">{{ line.qty_balance }}</td><td class="num">{{ line.unit_price|floatformat:2 }}</td><td class="num">{{ line.line_total|floatformat:2 }}</td></tr>{% endfor %}</tbody>
<tfoot><tr><td colspan="7" class="grand-label">Voucher total</td><td class="grand-value">{{ voucher.amount|floatformat:2 }}</td></tr></tfoot>
</table>
<table class="signatures"><tr>
<td><div class="line">{{ voucher.officer_name }}</div><div class="hint">Receiving Officer</div></td>
<td style="width:10%"></td>
<td><div class="line">{{ voucher.gm_authority_name|default:"________________________" }}</div><div class="hint">Authorised by — General Manager</div></td>
</tr></table>
<p class="footer-note">Voucher — {{ voucher.voucher_no }}</p>
</div></div>
<script>window.addEventListener('load',function(){setTimeout(function(){window.print()},500)});</script>
</body></html>
"""
Path("templates/adhoc_officer_voucher_print.html").write_text(adhoc_new, encoding="utf-8")
print("ro adhoc done")
