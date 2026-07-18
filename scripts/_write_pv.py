from pathlib import Path
CONTENT = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Payment Voucher {{ voucher.pay_order_no }}</title>
<style>
body{font-family:'Times New Roman',serif;color:#000;margin:0;line-height:1.55;font-size:14px;background:#fff}
.pioneer-letterhead{text-align:center;border-bottom:3px double #000;padding-bottom:14px;margin-bottom:28px}
.pioneer-letterhead .brand{margin:0;font-size:26px;font-weight:bold;letter-spacing:3px;text-transform:uppercase}
.pioneer-letterhead .division{margin:6px 0 0 0;font-size:13px;font-weight:bold;color:#334155;text-transform:uppercase}
.pioneer-letterhead .doc-type{margin:8px 0 0 0;font-size:12px;color:#475569;text-transform:uppercase}
.memo-block{display:grid;grid-template-columns:170px 1fr;gap:4px 0;margin-bottom:22px}
.memo-block strong{text-transform:uppercase}
table{width:100%;border-collapse:collapse;margin:18px 0 24px 0;font-size:13px}
th,td{border:1px solid #000;padding:9px 10px;text-align:left}
th{background:#f0f0f0;text-transform:uppercase;font-size:11px}
.num{text-align:right}
.signatures{display:grid;grid-template-columns:1fr 1fr;gap:48px;margin-top:42px}
.sign-line{border-top:1px solid #000;margin-top:48px;padding-top:6px;font-weight:bold}
.screen-toolbar{padding:16px 24px;background:#0f172a;display:flex;gap:12px;justify-content:flex-end}
.screen-toolbar button,.screen-toolbar a{padding:10px 18px;font-size:13px;text-decoration:none;border-radius:6px;font-weight:600;color:#fff;background:#2563eb;border:none;cursor:pointer}
.screen-toolbar button{background:#10b981}
@media print{.screen-toolbar{display:none!important}body{margin:0}@page{margin:18mm}}
</style>
</head>
<body>
<div class="screen-toolbar">
<button type="button" onclick="window.print()">Print Voucher</button>
<a href="{{ grn_list_url }}">Back to GRN Listing</a>
</div>
<div style="padding:36px 44px;">
<div class="pioneer-letterhead">
<h1 class="brand">Pioneer Operations Command</h1>
<p class="division">Accounts Payable — Procurement Settlement</p>
<p class="doc-type">Payment Input Voucher — {{ voucher.pay_order_no }}</p>
</div>
<div class="memo-block">
<strong>Voucher No:</strong><div>{{ voucher.pay_order_no }}</div>
<strong>Date:</strong><div>{{ voucher.created_at|date:"F d, Y" }}</div>
<strong>Payee:</strong><div>{% if supplier %}{{ supplier.description }}{% endif %}</div>
<strong>GRN Ref:</strong><div>{{ grn.grn_no }}</div>
<strong>LPO Ref:</strong><div>{{ lpo.lpo_no }}</div>
<strong>Invoice No:</strong><div>{{ grn.invoice_ref }}</div>
<strong>Task:</strong><div>{{ task.project_id }} — {{ task.description }}</div>
<strong>Amount:</strong><div><strong>US$ {{ amount|floatformat:2 }}</strong></div>
<strong>Payment Method:</strong><div>{{ voucher.get_payment_method_display }}</div>
<strong>Source Bank:</strong><div>{{ voucher.source_bank.description }} (A/C {{ voucher.source_bank.account_number }})</div>
{% if voucher.payment_method == "BANK" %}
<strong>Transfer Ref:</strong><div>{{ voucher.transfer_reference }}</div>
{% elif voucher.payment_method == "CHQ" %}
<strong>Cheque No:</strong><div>{{ voucher.cheque_number }}</div>
{% endif %}
{% if voucher.prepared_by_name %}<strong>Prepared By:</strong><div>{{ voucher.prepared_by_name }}</div>{% endif %}
{% if voucher.payment_notes %}<strong>Notes:</strong><div>{{ voucher.payment_notes }}</div>{% endif %}
</div>
<p>Authorise payment of <strong>US$ {{ amount|floatformat:2 }}</strong> to the supplier named above in settlement of GRN <strong>{{ grn.grn_no }}</strong> against invoice <strong>{{ grn.invoice_ref }}</strong>.</p>
<table>
<thead><tr><th>#</th><th>Description</th><th>UOM</th><th class="num">Qty Rcvd</th><th class="num">Unit</th><th class="num">Line Total</th></tr></thead>
<tbody>
{% for line in receipt_lines %}
<tr><td>{{ forloop.counter }}</td><td>{{ line.desc }}</td><td>{{ line.uom }}</td><td class="num">{{ line.this_receipt }}</td><td class="num">{{ line.price }}</td><td class="num">{{ line.total }}</td></tr>
{% endfor %}
</tbody>
</table>
<div class="signatures">
<div><p><strong>Prepared by (Accounts):</strong></p><div class="sign-line">{{ voucher.prepared_by_name|default:"________________________" }}</div><p>Signature: ________________________</p></div>
<div><p><strong>Authorised by (Director / GM):</strong></p><div class="sign-line">________________________</div><p>Signature: ________________________</p></div>
</div>
</div>
<script>window.addEventListener('load',function(){setTimeout(function(){window.print()},500)})</script>
</body></html>"""
Path("templates/payment_voucher_print.html").write_text(CONTENT, encoding="utf-8")
print("ok")
