"""
URL configuration for UN_accounting_system project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))

from django.contrib import admin
from django.urls import path

urlpatterns = [
    path('admin/', admin.site.urls),
]
"""
import os
from django.contrib import admin
from django.urls import path
from accounts import views
from django.conf import settings
from django.conf.urls.static import static


urlpatterns = [
    path('health/', views.health, name='health'),
    # --- CORE & DASHBOARDS ---
    path('admin/', admin.site.urls),
    path('', views.home, name='home'),
    path('login/', views.CustomLoginView.as_view(), name='login'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('docs/android-rollout-plan/', views.android_rollout_plan_doc, name='android_rollout_plan_doc'),
    path('api/switch-organization/', views.switch_active_organization, name='switch_active_organization'),
    path('ops-dashboard/', views.fin_mgmt_ops_view, name='ops_dashboard'),

    # --- PIONEER WORKFLOW ---
    # 1. The Senior Site Manager View (YOUR WORKING BOM)
    path('bom-builder/', views.bom_builder, name='bom_builder'),
    path('print-bom/', views.print_bom_view, name='print_bom'),
    path('print-bom/pdf/', views.print_bom_pdf_view, name='print_bom_pdf'),

    # 2. Requisition Order (THE NEW BRIDGE)
    path('ro-builder/', views.ro_builder, name='ro_builder'),
    path('ro-fetch/<int:ro_id>/', views.fetch_bom_to_ro, name='fetch_bom_to_ro'),
    path('ro-print/<int:ro_id>/', views.print_ro_view, name='print_ro_view'),
    
    # 3. RFQ Operations
    path('rfq-manager/', views.rfq_manager, name='rfq_manager'),
    path('rfq-manager/print-memo/<str:task_id>/', views.print_memo_view, name='print_memo'),
    path('rfq-manager/print-letter/', views.print_rfq_letter, name='print_rfq_letter'),
    
    # =========================================================
    # 4. CONSOLIDATED COMPETITIVE BIDDING (Isolate & Guarded)
    path('procurement/lpo-settlement/', views.procurement_lpo, name='procurement_lpo_settlement'),

    # =========================================================
    # In your urls.py inside UN_accounting_system
    path('bid-evaluation/print-preview/', views.print_lpo_preview, name='print_lpo_preview'),
    
    # 5. Procurement & Logistics
    path('ro/<int:ro_id>/print-bom/', views.print_bom_from_ro, name='print_bom_from_ro'),
    
    # FIXED: Pointed directly to the cockpit view that handles query strings (?task_id=)
    path('bid-evaluation/', views.bid_evaluation_terminal_view, name='bid_evaluation_terminal'),
    
    # --- ADD THIS TO YOUR URLS.PY Misc Purchases ---
    # path('misc-purchase/', views.misc_purchase_builder, name='misc_purchase'),
    
    
    # =======================================================
    # Ad -hoc Misc Purchases
    
    # =======================================================
    
    # 1. The Builder (Where Mr. Omambo drafts the list)
    path('misc-purchase/', views.misc_purchase_builder, name='misc_purchase_builder'),
    path('misc-purchase/register-supplier/', views.misc_register_supplier_ajax, name='misc_register_supplier'),
    
    
    # 2. The GM Executive Memo (Review before locking)
    path('ad-hoc-memo/', views.ad_hoc_purchase_memo_view, name='ad_hoc_memo'),
    
    # 3. The Action Endpoint (Locks budget in DB, redirects to print)
    path('authorize-mpo/', views.authorize_mpo_action, name='authorize_mpo'),
    
    # 4. The Print Audit Trail
    path('print-mpo/<uuid:mpo_id>/', views.print_mpo_view, name='print_mpo'),
    path('print-mpo/<uuid:mpo_id>/pdf/', views.print_mpo_pdf_view, name='print_mpo_pdf'),
    path('print-mro/<uuid:mro_id>/', views.print_mro_view, name='print_mro'),
    path('print-mro/<uuid:mro_id>/pdf/', views.print_mro_pdf_view, name='print_mro_pdf'),
    
    # 5. The Financial Dashboard
    path('misc-budget-actuals/', views.misc_budget_actuals_view, name='misc_budget_actuals'),
    path('print-fluid-ro/', views.print_fluid_ro_view, name='print_fluid_ro'),
    path('print-fluid-ro/pdf/', views.print_fluid_ro_pdf_view, name='print_fluid_ro_pdf'),
    
    # 6. LPO History Browser (Current + Previous LPOs)
    path('lpos/', views.lpo_list_view, name='lpo_list_view'),

    # 7. Budget vs Actuals Financial Control Dashboard
    path('budget-actuals/', views.budget_overview, name='budget_overview'),
    path('budget-approval/', views.budget_approval_view, name='budget_approval'),
    path(
        'ceo-fund-release/voucher/<uuid:release_id>/print/',
        views.print_ceo_fund_release_voucher_view,
        name='print_ceo_fund_release_voucher',
    ),

    # GM AIE — Accounting, Ops & Maintenance disbursement (Major + Ad-Hoc tasks)
    path('gm-disbursement/', views.gm_aie_disbursement_view, name='gm_aie_disbursement'),
    
    path('lpo/print/<int:lpo_id>/', views.print_lpo_view, name='print_lpo_view'),
    path('grn/print/<int:grn_id>/', views.print_grn_view, name='print_grn_view'),
    path('payment-voucher/print/<int:voucher_id>/', views.print_payment_voucher_view, name='print_payment_voucher_view'),
    path('adhoc-officer-voucher/print/<int:voucher_id>/', views.print_adhoc_officer_voucher_view, name='print_adhoc_officer_voucher_view'),
    path('lpo/commit/<int:task_id>/', views.commit_lpo, name='commit_lpo'),
    
    # PDF export must be before any lpo-dispatch/<slug>/ catch-all
    path('lpo-dispatch/pdf/', views.lpo_export_pdf, name='lpo_export_pdf'),
    path('lpo-dispatch/', views.procurement_lpo, name='procurement_lpo_view'),

    # =======================================================


    # --- CRUD & API ENGINE (The Lambda Section) ---
    path('users/', lambda r: views.get_entity_list(r, 'user'), name='user_list'),
    path('users/create/', lambda r: views.unified_api_create(r, 'user'), name='create_user'),
    path('roles/', lambda r: views.get_entity_list(r, 'role'), name='role_list'),
    path('roles/create/', lambda r: views.unified_api_create(r, 'role'), name='create_role'),
    path('bank/', lambda r: views.get_entity_list(r, 'bank'), name='bank_list'),
    path('bank/create/', lambda r: views.unified_api_create(r, 'bank'), name='create_bank'),
    path('bank/delete/<str:pk>/', lambda r, pk: views.delete_entity(r, 'bank', pk), name='delete_bank'),
    path('supplier/create/', lambda r: views.unified_api_create(r, 'supplier'), name='create_supplier'),
    path('analysis/create/', lambda r: views.unified_api_create(r, 'analysis'), name='create_analysis'),
    path('gl/create/', lambda r: views.unified_api_create(r, 'gl'), name='create_gl'),
    path('task/create/', lambda r: views.unified_api_create(r, 'task'), name='create_task'),
    path('build/create/', lambda r: views.unified_api_create(r, 'build'), name='create_build'),
    path('product/create/', lambda r: views.unified_api_create(r, 'product'), name='create_product'),
    path('app-settings/save/', lambda r: views.unified_api_create(r, 'app_settings'), name='save_app_settings'),
    path('organization/create/', lambda r: views.unified_api_create(r, 'organization'), name='create_organization'),
    
    # Add this line specifically for the search:
    path('api/supplier-lookup/', views.supplier_lookup, name='supplier_lookup'),
    path(
        'bid-evaluation/',
        views.bid_evaluation_terminal_view,
        name='bid_evaluation_terminal'
    ),

    path(
        'procurement/lpo-settlement/',
        views.procurement_lpo,
        name='procurement_lpo_settlement'
    ),
    
    path(
        'procurement/authorization/<str:task_id>/',
        views.print_memo_view,
        name='procurement_authorization'
    ),

    # --- SHARED API ---
    path('api/create/<str:entity_type>/', views.unified_api_create, name='api_create'),
    path('api/list/<str:entity_type>/', views.get_entity_list, name='api_get_list'),
    path('api/detail/<str:entity_type>/<str:pk>/', views.get_entity_detail, name='api_detail'),
    path('api/delete/<str:entity_type>/<str:pk>/', views.delete_entity, name='api_delete'),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static('/static/', document_root=os.path.join(settings.BASE_DIR, 'static'))
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)