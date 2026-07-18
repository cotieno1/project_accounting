# ============================================================================
# accounts/views.py  — BRIDGE FILE
#
# STEP 2 of the safe split migration.
#
# This file re-exports every public view function from the new modules.
# urls.py continues to import from `accounts.views` — nothing breaks.
# Railway keeps running. No URL routes change.
#
# HOW TO USE THIS:
#   1. Create all 6 module files (views_shared, views_auth, views_bom,
#      views_proc, views_misc, views_budget, views_bw)
#   2. Paste the correct functions from the original views.py into each module
#   3. REPLACE the original views.py with THIS file
#   4. Deploy to Railway — system runs exactly as before
#   5. Later (Step 3): update urls.py to import directly from modules,
#      then delete this bridge file
#
# ── STEP 3 (future): update urls.py like this: ───────────────────────────────
#   from accounts.views_auth import (
#       CustomLoginView, home, health, dashboard, create_user, ...
#   )
#   from accounts.views_bom import (
#       ro_builder, bom_builder, print_bom_view, ...
#   )
#   from accounts.views_proc import (
#       rfq_manager, bid_evaluation_view, procurement_lpo, ...
#   )
#   from accounts.views_misc import (
#       misc_purchase_builder, authorize_mpo_action, ...
#   )
#   from accounts.views_budget import (
#       budget_overview, gm_aie_disbursement_view, budget_approval_view, ...
#   )
#   from accounts.views_bw import (
#       infra_project_list, infra_project_dashboard, infra_project_create, ...
#   )
# ─────────────────────────────────────────────────────────────────────────────

# ── Auth, users, dashboard, master data, BuildWatch registration ──────────────
from .views_auth import (
    CustomLoginView,
    has_module_access,
    home,
    health,
    health_email,
    set_password_onboarding,
    password_change_required,
    resend_onboarding_email,
    android_rollout_plan_doc,
    dashboard,
    switch_active_organization,
    fin_mgmt_ops_view,
    get_pioneer_model,
    unified_api_create,
    get_entity_list,
    get_entity_detail,
    delete_entity,
    create_user,
    supplier_lookup,
    buildwatch_register,
    buildwatch_register_pending,
)

# ── BOM builder, RO builder, print flows ─────────────────────────────────────
from .views_bom import (
    generate_ro_no,
    ro_builder,
    fetch_bom_to_ro,
    confirm_ro,
    print_ro_draft_view,
    print_ro_view,
    bom_builder,
    print_bom_view,
    print_bom_pdf_view,
    print_bom_from_ro,
)

# ── Procurement: RFQ, bid eval, LPO, GRN, payment voucher ────────────────────
from .views_proc import (
    rfq_manager,
    bid_evaluation_view,
    procurement_lpo,
    lpo_export_pdf,
    lpo_list_view,
    lpo_settlement_view,
    print_memo_view,
    print_lpo_view,
    print_rfq_letter,
    print_rfq_letter_pdf,
    print_grn_view,
    print_payment_voucher_view,
    bid_evaluation_terminal_view,
    print_lpo_preview,
    sync_procurement_chain,
    commit_lpo,
)

# ── Misc / self-execute: MPO, MRO, officer vouchers ──────────────────────────
from .views_misc import (
    misc_register_supplier_ajax,
    misc_purchase_builder,
    ad_hoc_purchase_memo_view,
    print_fluid_ro_view,
    print_fluid_ro_pdf_view,
    print_mpo_view,
    print_mpo_pdf_view,
    print_mro_view,
    print_mro_pdf_view,
    print_adhoc_officer_voucher_view,
    misc_budget_actuals_view,
    authorize_mpo_action,
)

# ── Budget, CEO AIE, fund release, GM disbursement, GL ledger ─────────────────
from .views_budget import (
    budget_overview,
    gm_aie_disbursement_view,
    print_ceo_fund_release_voucher_view,
    budget_approval_view,
    fund_ledger_view,
    print_fund_ledger_view,
    print_gm_ceo_budget_memo_view,
)

# ── BuildWatch Sprint 1 ───────────────────────────────────────────────────────
from .views_bw import (
    infra_project_list,
    infra_project_dashboard,
    infra_project_create,
    isiolo_stadium_pilot,
)

# ── Shared helpers re-exported for any template tags or other modules ─────────
from .views_shared import (
    _task_from_request,
    _task_id_from_request,
    _resolve_project_task,
    _bid_eval_active_task,
    _money,
    _build_task_budget_status,
    _save_task_budget,
    _task_budget_record,
    _ops_cross_task_activity_feed,
)
