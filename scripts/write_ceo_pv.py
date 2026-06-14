from pathlib import Path
Path("templates/ceo_fund_release_voucher_print.html").write_text("""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>PV {{ pv_no }} — Task {{ task.project_id }}</title>
{% include "includes/correspondence_theme.html" %}
<style>
.voucher-sheet { padding: 32px 40px; page-break-after: always; box-sizing: border-box; }
.voucher-sheet:last-of-type { page-break-after: avoid; }
.memo-body p { margin: 0 0 14px; text-align: justify; font-size: 10pt; }
.budget-only-table tfoot td { font-weight: bold; background: #f1f5f9; }
.ceo-sign-block { margin-top: 48px; page-break-inside: avoid; }
</style>
</head>
<body class="correspondence-doc">
<div class="screen-toolbar no-print">
<button type="button" onclick="window.print()">Print voucher &amp; memo</button>
<a href="{{ back_url }}" class="toolbar-muted">Back to Budget Authorization</a>
</div>

<div class="voucher-sheet">
<div class="brand-bar"></div>
{% include "includes/print_correspondence_header.html" %}
<p class="print-doc-subtitle" style="text-align:center;margin:-8px 0 20px;">Internal Memorandum — Fund Disbursement to GM Accounting</p>
<div class="memo-block">
<strong>Date:</strong><div>{{ release.released_at|date:"F d, Y" }}</div>
<strong>To:</strong><div>{{ release.to_officer }}</div>
<strong>From:</strong><div>{{ release.from_office }}</div>
<strong>Re:</strong><div>Disbursement of authorized funds — Task {{ task.project_id }}</div>
<strong>PV No:</strong><div><span class="ref-highlight">{{ pv_no }}</span></div>
<strong>Task ID:</strong><div>{{ task.project_id }}</div>
<strong>Project:</strong><div>{{ task.description }}</div>
<strong>AIE Ref:</strong><div>{{ ceo_aie_reference|default:"—" }}</div>
</div>
<div class="memo-body">
<p>Dear General Manager,</p>
<p>This memorandum confirms the <strong>Authority to Incur Expenditure (AIE)</strong> release of funds for <strong>Task {{ task.project_id }} — {{ task.description }}</strong>. The CEO has authorized a bank transfer of <strong>US$ {{ release.amount|floatformat:2 }}</strong> to your office for accounting, operations, and maintenance disbursements strictly against the CEO-approved budget attached herein.</p>
<p>Bank transfer reference: <strong>{{ release.bank_reference }}</strong>. Payment voucher number: <strong>{{ pv_no }}</strong>.</p>
<p>You may commence GM disbursements only against the four locked budget lines shown in the schedule below. Retain this memo and voucher for audit.</p>
<p>Respectfully,</p>
</div>
<div class="ceo-sign-block">
<div class="sign-line">{{ ceo_name|default:"Chief Executive Officer" }}</div>
<p class="sign-role">CEO — Authority to Incur Expenditure (AIE)</p>
<p style="font-size:9pt;color:#64748b;margin-top:8px;">Date: {{ release.released_at|date:"F d, Y" }}</p>
</div>
</div>

<div class="voucher-sheet">
<div class="brand-bar"></div>
{% include "includes/org_letterhead.html" %}
<p class="print-doc-subtitle" style="text-align:center;margin:-8px 0 20px;">Payment Voucher — Fund Transfer to GM (Task {{ task.project_id }})</p>
<div class="memo-block">
<strong>PV No:</strong><div><span class="ref-highlight">{{ pv_no }}</span></div>
<strong>Date:</strong><div>{{ release.released_at|date:"F d, Y" }}</div>
<strong>Task ID:</strong><div>{{ task.project_id }}</div>
<strong>Project description:</strong><div>{{ task.description }}</div>
<strong>Payee:</strong><div>{{ release.to_officer }}</div>
<strong>Payer:</strong><div>{{ release.from_office }}</div>
<strong>Amount (US$):</strong><div><strong>{{ release.amount|floatformat:2 }}</strong></div>
<strong>Method:</strong><div>Bank transfer</div>
<strong>Bank reference:</strong><div>{{ release.bank_reference }}</div>
<strong>AIE memo:</strong><div>{{ ceo_aie_reference|default:"—" }}</div>
<strong>Budget ref:</strong><div>{{ budget_label }} (v{{ budget_version }})</div>
</div>
<p style="font-size:10pt;margin-bottom:16px;">Authorize and record transfer of <strong>US$ {{ release.amount|floatformat:2 }}</strong> to <strong>{{ release.to_officer }}</strong> for project execution under Task <strong>{{ task.project_id }}</strong>.</p>
<span class="nav-label" style="display:block;margin:20px 0 10px;color:#1e3a8a;font-size:11px;text-transform:uppercase;letter-spacing:0.05em;">CEO-authorized budget schedule (provision only — no actuals)</span>
<table class="budget-only-table">
<thead>
<tr><th>Budget line</th><th class="num" style="text-align:right;">Authorized amount (US$)</th></tr>
</thead>
<tbody>
{% for line in provision_lines %}
<tr{% if forloop.counter|divisibleby:2 %} class="zebra"{% endif %}>
<td>{{ line.label }}</td>
<td class="num" style="text-align:right;font-family:monospace;">{{ line.budget|floatformat:2 }}</td>
</tr>
{% endfor %}
</tbody>
<tfoot>
<tr>
<td style="text-align:right;text-transform:uppercase;">Total authorized budget</td>
<td class="num" style="text-align:right;font-family:monospace;color:#1e3a8a;">{{ total_budget|floatformat:2 }}</td>
</tr>
</tfoot>
</table>
<div class="signatures" style="margin-top:40px;">
<div>
<p><strong>Prepared by (CEO Office):</strong></p>
<div class="sign-line">{{ ceo_name|default:"Chief Executive Officer" }}</div>
<p class="sign-role">AIE Holder — Budget Authorization</p>
</div>
<div>
<p><strong>Received by (GM Accounting):</strong></p>
<div class="sign-line">________________________</div>
<p class="sign-role">GM — Accounting Officer</p>
<p style="font-size:9pt;color:#64748b;">Date: ________________________</p>
</div>
</div>
<p style="text-align:center;font-size:8pt;color:#94a3b8;margin-top:24px;">Computer-generated — {{ pv_no }} — Task {{ task.project_id }} — {{ release.released_at|date:"Y-m-d" }}</p>
</div>
{% if auto_print %}
<script>window.addEventListener("load",function(){setTimeout(function(){window.print()},500)});</script>
{% endif %}
</body>
</html>
""", encoding="utf-8")
print("ok")
