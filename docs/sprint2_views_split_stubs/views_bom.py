# ============================================================================
# accounts/views_bom.py
#
# DOMAIN: BOM Builder, Requisition Orders, Print Flows
#
# Functions from original views.py:
#   generate_ro_no           line 1359
#   _ro_redirect             line 1375
#   _assert_ro_editable      line 1379
#   ro_builder               line 1389   ← PUBLIC VIEW
#   fetch_bom_to_ro          line 1462   ← PUBLIC VIEW
#   confirm_ro               line 1489   ← PUBLIC VIEW
#   print_ro_draft_view      line 1530   ← PUBLIC VIEW
#   print_ro_view            line 1547   ← PUBLIC VIEW
#   _task_on_major_bom_lane  line 1756
#   _task_is_new_for_bom     line 1775
#   _task_bom_draft_in_progress line 1788
#   _bom_active_task         line 1797
#   _bom_can_start_bom       line 1816
#   _bom_task_sidebar_hint   line 1827
#   _bom_builder_task_rows   line 1877
#   _bom_task_status_snapshot line 1891
#   _bom_screen_lane         line 2075
#   _get_task_bom            line 2085
#   _task_meaningful_bom_header line 2106
#   _bom_page_heading        line 2151
#   bom_builder              line 2200   ← PUBLIC VIEW
#   _bom_print_context       line 2413
#   print_bom_view           line 2447   ← PUBLIC VIEW
#   print_bom_pdf_view       line 2462   ← PUBLIC VIEW
#   print_bom_from_ro        line 3231   ← PUBLIC VIEW
#
# ~900 lines
# ============================================================================

from .views_shared import *


# ── PASTE from views.py: lines 1359–1461 (generate_ro_no → ro_builder) ───────
# Then: lines 1462–1558 (fetch_bom_to_ro, confirm_ro, print_ro_* views)
# Then: lines 1756–2480 (all _bom_* helpers and bom_builder)
# Then: lines 2447–2480 (print_bom_view, print_bom_pdf_view)
# Then: lines 3231–3290 (print_bom_from_ro)
#
# Instructions:
#   Open views.py, copy each range, paste in order below.
#   The `from .views_shared import *` at the top supplies all imports.
#   No additional import statements needed.
# ─────────────────────────────────────────────────────────────────────────────
