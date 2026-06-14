from pathlib import Path
Path("templates/ceo_fund_release_voucher_print.html").write_text("""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>PV {{ pv_no }} — Task {{ task.project_id }}</title>
{% include "includes/lpo_document_styles.html" %}
</head>
<body class="pioneer-doc-print">
<div class="screen-toolbar no-print">
<button type="button" onclick="window.print()">Print voucher &amp; memo</button>
<a href="{{ back_url }}" class="toolbar-muted">Back to Budget Authorization</a>
</div>

<div class="lpo-paper lpo-sheet">
<div class="doc">
<div class="brand-bar"></div>
{% include "includes/pioneer_letterhead_block.html" with doc_subtitle="Internal Memorandum — Fund Disbursement to GM Accounting" %}
<table class="meta-table">
<tr><th style="width:34%">Document</th><th style="width:33%">Payment Voucher No.</th><th style="width:33%">Date</th></tr>
<tr><td>CEO Fund Disbursement Memo</td><td class="lpo-no">{{ pv_no }}</td><td>{{ release.released_at|date:"F d, Y" }}</td></tr>
</table>
<table class="parties">
<tr><th style="width:50%">To</th><th style="width:50%">From</th></tr>
<tr>
<td><div class="party-name">{{ release.to_officer }}</div><div class="muted">General Manager — Accounting</div></td>
<td><div class="party-name">{{ release.from_office }}</div><div class="muted">AIE reference: {{ ceo_aie_reference|default:"—" }}</div></td>
</tr>
</table>
<table class="meta-table">
<tr><th>Task ID</th><th>Project description</th><th>Transfer amount (US$)</th></tr>
<tr>
<td>{{ task.project_id }}</td>
<td>{{ task.description }}</td>
<td class="lpo-no" style="font-family:monospace;">{{ release.amount|floatformat:2 }}</td>
</tr>
</table>
<div class="terms">
<strong>Cover memorandum</strong>
<div class="memo-body">
<p>Dear General Manager,</p>
<p>This memorandum confirms the <strong>Authority to Incur Expenditure (AIE)</strong> release of funds for <strong>Task {{ task.project_id }} — {{ task.description }}</strong>. The CEO has authorized a bank transfer of <strong>US$ {{ release.amount|floatformat:2 }}</strong> to your office for accounting, operations, and maintenance disbursements strictly against the CEO-approved budget on the attached payment voucher.</p>
<p>Bank transfer reference: <strong>{{ release.bank_reference }}</strong>. Payment voucher: <strong>{{ pv_no }}</strong>.</p>
<p>You may commence GM disbursements only against the four locked budget lines in the schedule. Retain this memo and voucher for audit.</p>
<p>Respectfully,</p>
</div>
</div>
<table class="signatures">
<tr>
<td><div class="line">{{ ceo_name|default:"Chief Executive Officer" }}</div><div class="hint">CEO — Authority to Incur Expenditure (AIE)</div></td>
<td style="width:10%"></td>
<td><div class="line">Date</div><div class="hint">{{ release.released_at|date:"F d, Y" }}</div></td>
</tr>
</table>
<p class="footer-note">Memo — {{ pv_no }} — Task {{ task.project_id }}</p>
</div>
</div>

<div class="lpo-paper lpo-sheet">
<div class="doc">
<div class="brand-bar"></div>
{% include "includes/pioneer_letterhead_block.html" with doc_subtitle="Payment Voucher — Fund Transfer to GM Accounting" %}
<table class="meta-table">
<tr><th style="width:34%">Document</th><th style="width:33%">PV No.</th><th style="width:33%">Date of issue</th></tr>
<tr><td>Fund Transfer Payment Voucher</td><td class="lpo-no">{{ pv_no }}</td><td>{{ release.released_at|date:"F d, Y" }}</td></tr>
</table>
<table class="parties">
<tr><th style="width:50%">Payee</th><th style="width:50%">Payer / Project</th></tr>
<tr>
<td>
<div class="party-name">{{ release.to_officer }}</div>
<div class="muted">Bank ref: {{ release.bank_reference }}</div>
<div class="muted">Method: Bank transfer</div>
</td>
<td>
<div class="party-name">Task {{ task.project_id }}</div>
<div class="muted">{{ task.description }}</div>
<div class="muted" style="margin-top:8px;"><strong>From:</strong> {{ release.from_office }}</div>
<div class="muted"><strong>Budget:</strong> {{ budget_label }} (v{{ budget_version }})</div>
</td>
</tr>
</table>
<table class="lines">
<thead>
<tr><th style="width:58%">Budget line (CEO authorized — provision only)</th><th class="num" style="width:42%">Amount (US$)</th></tr>
</thead>
<tbody>
{% for line in provision_lines %}
<tr{% if forloop.counter|divisibleby:2 %} class="zebra"{% endif %}>
<td>{{ line.label }}</td>
<td class="num">{{ line.budget|floatformat:2 }}</td>
</tr>
{% endfor %}
</tbody>
<tfoot>
<tr>
<td class="grand-label">Total authorized budget</td>
<td class="grand-value">{{ total_budget|floatformat:2 }}</td>
</tr>
<tr>
<td class="grand-label">Transfer amount (this voucher)</td>
<td class="grand-value">{{ release.amount|floatformat:2 }}</td>
</tr>
</tfoot>
</table>
<div class="terms">
<strong>Authorization note</strong>
Authorize and record transfer of <strong>US$ {{ release.amount|floatformat:2 }}</strong> to <strong>{{ release.to_officer }}</strong> for project execution under Task <strong>{{ task.project_id }}</strong>. AIE memo: <strong>{{ ceo_aie_reference|default:"—" }}</strong>.
</div>
<table class="signatures">
<tr>
<td><div class="line">{{ ceo_name|default:"Chief Executive Officer" }}</div><div class="hint">Prepared by — CEO Office (AIE)</div></td>
<td style="width:10%"></td>
<td><div class="line">________________________</div><div class="hint">Received by — GM Accounting Officer</div></td>
</tr>
</table>
<p class="footer-note">Computer-generated — {{ pv_no }} — Task {{ task.project_id }} — {{ release.released_at|date:"Y-m-d" }}</p>
</div>
</div>
{% if auto_print %}
<script>window.addEventListener("load",function(){setTimeout(function(){window.print()},500)});</script>
{% endif %}
</body>
</html>
""", encoding="utf-8")
print("ceo ok")
