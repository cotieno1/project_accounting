# ============================================================================
# accounts/views_budget.py
#
# DOMAIN: Budget, CEO AIE, Fund Release, GM Disbursement, GL Ledger
#
# This is the consultant/QS financial control engine:
#   "Budget drawn up → CEO approval → funds released → GM disburses
#    → GL posted → value for money ensured"
#
# Functions from original views.py:
#   _task_lpo_paid_total         line 6935
#   _task_budget_actual_spend    line 6951
#   budget_overview              line 6969   ← PUBLIC VIEW
#   _next_disbursement_payment_number line 7329
#   _task_grn_received_total     line 7341
#   _task_has_major_procurement  line 7354
#   _task_project_class          line 7362
#   _disbursement_line_budget_amount line 7376
#   _disbursement_line_actual    line 7401
#   _task_disbursement_budget_summary line 7423
#   _disbursement_payment_listing line 7461
#   _gm_funds_available          line 7478
#   _gm_desk_blocked             line 7487
#   _gm_resolve_active_task      line 7496
#   _gm_task_sidebar_capabilities line 7505
#   _gm_budget_compliance_hold   line 7556
#   _gm_send_ceo_budget_reminder line 7679
#   gm_aie_disbursement_view     line 7751   ← PUBLIC VIEW (~190 lines)
#   _next_fund_release_number    line 7939
#   _task_budget_provision_lines line 7956
#   _build_ceo_fund_release_voucher_context line 7974
#   _ceo_fund_release_print_template line 8008
#   print_ceo_fund_release_voucher_view line 8015 ← PUBLIC VIEW
#   budget_approval_view         line 8029   ← PUBLIC VIEW (~215 lines)
#   _can_view_fund_ledger        line 8242
#   _fund_ledger_context         line 8248
#   fund_ledger_view             line 8278   ← PUBLIC VIEW
#   print_fund_ledger_view       line 8286   ← PUBLIC VIEW
#   print_gm_ceo_budget_memo_view line 8294  ← PUBLIC VIEW
#
# ~1,600 lines
# ============================================================================

from .views_shared import *


# ── PASTE from views.py — in this order: ─────────────────────────────────────
#
#   Lines 6935–6968   _task_lpo_paid_total, _task_budget_actual_spend
#   Lines 6969–7006   budget_overview
#   Lines 7329–7560   _next_disbursement_payment_number,
#                     _task_grn_received_total, _task_has_major_procurement,
#                     _task_project_class, _disbursement_line_budget_amount,
#                     _disbursement_line_actual,
#                     _task_disbursement_budget_summary,
#                     _disbursement_payment_listing,
#                     _gm_funds_available, _gm_desk_blocked,
#                     _gm_resolve_active_task,
#                     _gm_task_sidebar_capabilities,
#                     _gm_budget_compliance_hold
#   Lines 7679–7940   _gm_send_ceo_budget_reminder, gm_aie_disbursement_view
#   Lines 7939–8030   _next_fund_release_number,
#                     _task_budget_provision_lines,
#                     _build_ceo_fund_release_voucher_context,
#                     _ceo_fund_release_print_template,
#                     print_ceo_fund_release_voucher_view
#   Lines 8029–8242   budget_approval_view
#   Lines 8242–8332   _can_view_fund_ledger, _fund_ledger_context,
#                     fund_ledger_view, print_fund_ledger_view,
#                     print_gm_ceo_budget_memo_view
#
# Instructions:
#   Copy each range from views.py and paste in order below this comment.
#   `from .views_shared import *` supplies all imports — nothing else needed.
# ─────────────────────────────────────────────────────────────────────────────
