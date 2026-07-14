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

    # ── Bidder actions — login required ──────────────────────────────────
    path('<int:listing_id>/register/',
         t.tender_register,
         name='tender-register'),

    path('<int:listing_id>/boq/',
         t.tender_boq_download,
         name='tender-boq-download'),

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
