# ============================================================================
# accounts/views_misc.py
#
# DOMAIN: Misc / Self-Execute — MPO, MRO, Officer Vouchers, Ad-Hoc Purchases
#
# This is the constructor's self-execute engine:
#   "Internal team buys and builds — no RFQ needed"
#   Swimming pools, perimeter walls, site adjustments
#
# Functions from original views.py:
#   _mpo_ro_locked           line 1560
#   _mpo_has_ro_number       line 1569
#   _assert_mpo_editable     line 1576
#   _misc_display_mro_number line 1584
#   _misc_display_ro_number  line 1593
#   _misc_stage_b_onboarding_visible line 1599
#   _prune_empty_numbered_draft_mpos line 1624
#   _require_draft_mpo       line 1637
#   _misc_purchase_tasks     line 1654
#   _misc_purchase_task_list line 1664
#   _task_on_major_bom_lane  line 1699  (also used in views_bom — shared via views_shared)
#   _task_has_misc_po_path   line 1736
#   _task_on_major_procurement_lane line 1756
#   _misc_planned_budget     line 4912
#   _misc_locked_total       line 4928
#   _misc_ro_status_css      line 4941
#   _normalize_misc_qty      line 4951
#   _fmt_misc_qty            line 4959
#   _misc_qty_raw            line 4964
#   _misc_item_qty_purchased line 4969
#   _misc_mpo_all_lines_purchased line 4977
#   _misc_mark_mpo_disbursed_if_complete line 4987
#   _misc_mpo_purchase_status line 4993
#   _serialize_task_adhoc_ros_for_purchase line 5011
#   _serialize_task_officer_vouchers line 5122
#   _gm_officer_pv_return    line 5167
#   _gm_create_officer_payment_voucher line 5175
#   _gm_settle_officer_payment_voucher line 5315
#   _misc_create_officer_payment_voucher line 5388
#   print_adhoc_officer_voucher_view line 5539 ← PUBLIC VIEW
#   _misc_doc_return_url     line 5577
#   _misc_mro_document_urls  line 5583
#   _misc_mpo_ro_document_urls line 5597
#   _misc_adhoc_ro_listing   line 5614
#   _misc_task_mro_registry  line 5646
#   _misc_adhoc_actual_ro_total line 5706
#   _misc_adhoc_material_budget_status line 5719
#   _misc_budget_formulation line 5739
#   _misc_ceo_payment_voucher_gate line 5796
#   _get_task_baseline_mro   line 5835
#   _get_task_baseline_mpo   line 5847
#   _adhoc_material_total_from_mro_mpo line 5866
#   _adhoc_budget_ceiling    line 5885
#   _ensure_adhoc_provision_budget line 5891
#   _task_has_adhoc_baseline line 5942
#   _misc_default_gl         line 5946
#   _ensure_mpo_reference    line 5950
#   _get_active_draft_mpo    line 5958
#   _get_or_create_draft_mpo line 5967
#   _recalc_mpo_total        line 5997
#   _misc_supplier_session   line 6004
#   _save_misc_supplier_session line 6011
#   _mpo_supplier_label      line 6034
#   _apply_supplier_to_mpo   line 6045
#   _mpo_to_batch            line 6052
#   _sync_session_from_mpo   line 6077
#   _create_supplier_from_post line 6086
#   _next_mpo_number         line 6103
#   _next_mro_number         line 6114
#   misc_register_supplier_ajax line 6126 ← PUBLIC VIEW
#   misc_purchase_builder    line 6149   ← PUBLIC VIEW  (~500 lines — the core)
#   ad_hoc_purchase_memo_view line 6662  ← PUBLIC VIEW
#   print_fluid_ro_view      line 6695   ← PUBLIC VIEW
#   _fluid_ro_print_context  line 6716
#   print_fluid_ro_pdf_view  line 6770   ← PUBLIC VIEW
#   print_mpo_view           line 6798   ← PUBLIC VIEW
#   _mpo_print_context       line 6817
#   print_mpo_pdf_view       line 6841   ← PUBLIC VIEW
#   print_mro_view           line 6862   ← PUBLIC VIEW
#   _mro_print_context       line 6881
#   print_mro_pdf_view       line 6909   ← PUBLIC VIEW
#   authorize_mpo_action     line 7116   ← PUBLIC VIEW  (~150 lines)
#   _prune_duplicate_adhoc_mros line 7075
#   misc_budget_actuals_view line 7007   ← PUBLIC VIEW
#
# ~2,200 lines
# ============================================================================

from .views_shared import *


# ── PASTE from views.py — in this order: ─────────────────────────────────────
#
#   Lines 1560–1740   _mpo_* helpers, _misc_display_*, _misc_stage_*,
#                     _prune_empty_*, _require_draft_mpo, _misc_purchase_tasks,
#                     _misc_purchase_task_list
#   Lines 1736–1800   _task_has_misc_po_path, _task_on_major_procurement_lane
#   Lines 4912–5000   _misc_planned_budget → _misc_mpo_purchase_status
#   Lines 5011–5545   _serialize_task_adhoc_ros_for_purchase,
#                     _serialize_task_officer_vouchers,
#                     _gm_officer_pv_return, _gm_create_officer_payment_voucher,
#                     _gm_settle_officer_payment_voucher,
#                     _misc_create_officer_payment_voucher,
#                     print_adhoc_officer_voucher_view
#   Lines 5577–6130   All _misc_doc_*, _misc_mro_*, _misc_adhoc_*,
#                     _ensure_adhoc_*, _misc_default_gl, _ensure_mpo_*,
#                     _get_*_mpo, _recalc_mpo_total, _misc_supplier_*,
#                     _apply_supplier_*, _mpo_to_batch, _sync_session_*,
#                     _create_supplier_*, _next_mpo_number, _next_mro_number
#   Lines 6126–6935   misc_register_supplier_ajax, misc_purchase_builder,
#                     ad_hoc_purchase_memo_view, all print_*_view functions,
#                     _mpo_print_context, _mro_print_context,
#                     _fluid_ro_print_context
#   Lines 7007–7120   misc_budget_actuals_view, _prune_duplicate_adhoc_mros,
#                     authorize_mpo_action
#
# Instructions:
#   Copy each range from views.py and paste in order below this comment.
#   `from .views_shared import *` supplies all imports — nothing else needed.
# ─────────────────────────────────────────────────────────────────────────────
