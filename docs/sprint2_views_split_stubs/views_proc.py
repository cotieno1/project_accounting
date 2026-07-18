# ============================================================================
# accounts/views_proc.py
#
# DOMAIN: Procurement — RFQ, Bid Evaluation, LPO, GRN, Payment Voucher
#
# This is the constructor's procurement engine:
#   "Award to lowest bidder, track delivery, process payment"
#
# Functions from original views.py:
#   rfq_manager              line 2483   ← PUBLIC VIEW
#   bid_evaluation_view      line 2538   ← PUBLIC VIEW
#   _build_lpo_print_context line 2750
#   procurement_lpo          line 2814   ← PUBLIC VIEW
#   lpo_export_pdf           line 2837   ← PUBLIC VIEW
#   lpo_list_view            line 2875   ← PUBLIC VIEW
#   lpo_settlement_view      line 2895   ← PUBLIC VIEW
#   print_memo_view          line 3037   ← PUBLIC VIEW
#   print_lpo_view           line 3101   ← PUBLIC VIEW
#   _rfq_letter_context      line 3155
#   print_rfq_letter         line 3198   ← PUBLIC VIEW
#   print_rfq_letter_pdf     line 3208   ← PUBLIC VIEW
#   perform_procurement_sync line 3286
#   resolve_source_items     line 3375
#   _lpo_item_received_qty   line 3494
#   _lpo_receipt_status      line 3501
#   _serialize_task_lpos     line 3519
#   _serialize_lpo_goods_status line 3577
#   _grn_receipt_amount      line 3654
#   _parse_month_period      line 3661
#   _serialize_task_grns     line 3690
#   _serialize_task_payment_vouchers line 3767
#   _gm_disbursement_redirect line 3811
#   _banks_select_data       line 3819
#   _gm_create_payment_voucher line 3829
#   _bid_eval_cancel_lpo     line 3924
#   _bid_eval_create_grn     line 3937
#   _build_grn_print_context line 4027
#   print_grn_view           line 4087   ← PUBLIC VIEW
#   print_payment_voucher_view line 4149 ← PUBLIC VIEW
#   bid_evaluation_terminal_view line 4164 ← PUBLIC VIEW
#   print_lpo_preview        line 4359   ← PUBLIC VIEW
#   _task_rfq_records        line 4460
#   _bid_evaluation_gate     line 4472
#   _bid_evaluation_rfq_status line 4619
#   _bid_eval_budget_progress line 4657
#   _bid_evaluation_workspace line 4696
#   _task_budget_channel_info line 4856
#   sync_procurement_chain   line 7263
#   commit_lpo               line 7301   ← PUBLIC VIEW
#
# ~1,800 lines
# ============================================================================

from .views_shared import *


# ── PASTE from views.py — in this order: ─────────────────────────────────────
#
#   Lines 2483–2749   rfq_manager, bid_evaluation_view
#   Lines 2750–2835   _build_lpo_print_context
#   Lines 2814–2970   procurement_lpo, lpo_export_pdf, lpo_list_view,
#                     lpo_settlement_view
#   Lines 3036–3230   print_memo_view, print_lpo_view, _rfq_letter_context,
#                     print_rfq_letter, print_rfq_letter_pdf
#   Lines 3286–3500   perform_procurement_sync, resolve_source_items, _money
#   Lines 3494–3930   _lpo_* helpers, _serialize_*, _grn_*, _gm_create_*
#   Lines 3924–4165   _bid_eval_cancel_lpo, _bid_eval_create_grn,
#                     _build_grn_print_context, print_grn_view,
#                     print_payment_voucher_view, bid_evaluation_terminal_view
#   Lines 4359–4870   print_lpo_preview, _task_rfq_records,
#                     _bid_evaluation_gate, _bid_evaluation_rfq_status,
#                     _bid_eval_budget_progress, _bid_evaluation_workspace,
#                     _task_budget_channel_info
#   Lines 7263–7330   sync_procurement_chain, commit_lpo
#
# Instructions:
#   Copy each range from views.py and paste in order below this comment.
#   `from .views_shared import *` supplies all imports — nothing else needed.
# ─────────────────────────────────────────────────────────────────────────────
