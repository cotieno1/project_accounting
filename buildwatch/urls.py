# ============================================================================
# buildwatch/urls.py
#
# All BuildWatch + Tender Exchange URL routes.
# Include in UN_accounting_system/urls.py:
#
#   from django.urls import path, include
#   urlpatterns += [
#       path('buildwatch/', include('buildwatch.urls')),
#       path('tenders/',    include('buildwatch.urls_tenders')),
#   ]
# ============================================================================

from django.urls import path
from buildwatch import views_bw as bw
from buildwatch import views_tenders as t
from buildwatch import views_subcontract_portal as sub
from buildwatch import views_compliance as comp
from buildwatch import views_delivery as deliv
from buildwatch import views_execution as execn
from buildwatch import views_open_tender as ot

# ── BuildWatch core (Sprint 1) ────────────────────────────────────────────────
buildwatch_patterns = [
    path('projects/',
         bw.infra_project_list,
         name='infra-project-list'),

    path('projects/new/',
         bw.infra_project_create,
         name='infra-project-create'),

    path('projects/<int:project_id>/',
         bw.infra_project_dashboard,
         name='infra-project-dashboard'),

    path('isiolo/',
         bw.isiolo_stadium_pilot,
         name='isiolo-stadium-pilot'),
]

# ── Tender Exchange (Sprint 2) ────────────────────────────────────────────────
tender_patterns = [

    # ── Public — no login needed to browse ───────────────────────────────
    path('',
         t.tender_list,
         name='tender-list'),

    path('<int:listing_id>/',
         t.tender_detail,
         name='tender-detail'),

    path('sponsors/<str:org_code>/',
         t.sponsor_landing,
         name='sponsor-landing'),

    # ── Compliance & sign-off register ───────────────────────────────────
    path('<int:listing_id>/compliance/',
         comp.compliance_register,
         name='compliance-register'),

    path('<int:listing_id>/compliance/action/',
         comp.compliance_action,
         name='compliance-action'),

    path('<int:listing_id>/compliance/<int:checkpoint_id>/sample.pdf',
         comp.compliance_sample_certificate,
         name='compliance-sample-cert'),

    # ── Project Delivery Hub (award, payment certificates) ───────────────
    path('<int:listing_id>/delivery/action/',
         deliv.delivery_action,
         name='delivery-action'),

    path('<int:listing_id>/delivery/certificate/<int:cert_id>.pdf',
         deliv.payment_certificate_pdf,
         name='payment-certificate-pdf'),

    path('<int:listing_id>/delivery/sop/<int:sop_id>.pdf',
         deliv.sop_pdf,
         name='sop-pdf'),

    # ── Bidder actions — login required ──────────────────────────────────
    path('<int:listing_id>/register/',
         t.tender_register,
         name='tender-register'),

    path('<int:listing_id>/boq/',
         t.tender_boq_download,
         name='tender-boq-download'),

    path('<int:listing_id>/boq/load/',
         t.tender_load_pdf_boq,
         name='tender-load-pdf-boq'),

    path('<int:listing_id>/bid/',
         t.bid_workspace,
         name='bid-workspace'),

    path('<int:listing_id>/bid/self-assess/',
         t.bid_self_assess,
         name='bid-self-assess'),

    path('<int:listing_id>/bid/draft.pdf/',
         t.bid_draft_pdf,
         name='bid-draft-pdf'),

    path('<int:listing_id>/bid/submit/',
         t.bid_submit,
         name='bid-submit'),

    path('<int:listing_id>/bid/subcontract/',
         t.bid_subcontract,
         name='bid-subcontract'),

    path('<int:listing_id>/bid/subcontract/<int:pk>/',
         t.bid_subcontract_detail,
         name='bid-subcontract-detail'),

    path('<int:listing_id>/bid/subcontract/<int:pk>/agreement/',
         t.bid_subcontract_agreement,
         name='bid-subcontract-agreement'),

    path('<int:listing_id>/bid/subcontract/<int:pk>/agreement.pdf',
         t.bid_subcontract_agreement_pdf,
         name='bid-subcontract-agreement-pdf'),

    path('<int:listing_id>/bid/subcontract/<int:pk>/ack/',
         sub.subcontract_ack_quote,
         name='subcontract-ack-quote'),

    path('<int:listing_id>/bid/subcontract/<int:pk>/notify-award/',
         sub.subcontract_notify_award,
         name='subcontract-notify-award'),

    path('subcontract/portal/<str:token>/',
         sub.subcontract_portal,
         name='subcontract-portal'),

    path('subcontract/portal/<str:token>/draft.pdf/',
         sub.subcontract_portal_draft_pdf,
         name='subcontract-portal-draft-pdf'),

    path('subcontract/accept/<str:token>/',
         sub.subcontract_accept,
         name='subcontract-accept'),

    # ── Bidder dashboard ──────────────────────────────────────────────────
    path('my-bids/',
         t.my_bids,
         name='my-bids'),

    path('my-subcontracts/',
         t.my_subcontracts,
         name='my-subcontracts'),

    path('alerts/',
         t.tender_alerts,
         name='tender-alerts'),

    # ── Employer / Publisher actions — login required ─────────────────────
    path('publish/',
         t.tender_publish,
         name='tender-publish'),

    path('manage/<int:listing_id>/',
         t.tender_manage,
         name='tender-manage'),

    path('manage/<int:listing_id>/addendum/',
         t.tender_addendum,
         name='tender-addendum'),

    path('manage/<int:listing_id>/toggle-publish/',
         t.tender_publish_toggle,
         name='tender-publish-toggle'),
]

# ── Legacy internal execution (kept for old links; prefer open-tender dashboards)
internal_patterns = [
    path('',
         execn.works_execution_index,
         name='works-execution-index'),

    path('<int:listing_id>/',
         execn.works_execution,
         name='works-execution'),

    path('<int:listing_id>/action/',
         execn.works_execution_action,
         name='works-execution-action'),

    path('<int:listing_id>/subtask/<int:subtask_id>/certificate.pdf',
         execn.works_subtask_certificate_pdf,
         name='works-subtask-cert'),
]

# ── Open Tender - Financial Dashboard (BOQ + internal sub-tasks)
open_tender_patterns = [
    path('',
         ot.open_tender_dashboard,
         name='open-tender-dashboard'),
    path('from-listing/<int:listing_id>/',
         ot.create_open_tender_from_listing,
         name='open-tender-from-listing'),
    path('<str:task_id>/',
         ot.open_tender_detail,
         name='open-tender-detail'),
    path('<str:task_id>/action/',
         ot.open_tender_action,
         name='open-tender-action'),
]

# ── Public Tender Internal Fin Ops (phased products + resources)
public_fin_ops_patterns = [
    path('',
         ot.public_tender_fin_ops,
         name='public-tender-fin-ops-index'),
    path('<str:task_id>/',
         ot.public_tender_fin_ops,
         name='public-tender-fin-ops'),
    path('<str:task_id>/action/',
         ot.public_tender_fin_ops_action,
         name='public-tender-fin-ops-action'),
]
