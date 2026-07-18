# ============================================================================
# accounts/views_shared.py
#
# Shared imports, helpers and utility functions used across all view modules.
# Every module imports from here — nothing is duplicated.
#
# DO NOT add view functions here. Only pure helpers, no request handlers.
# ============================================================================

from django.utils import timezone
import secrets
import calendar
import re
import json
import ast
import os
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from django.contrib.auth.models import User
from django.http import JsonResponse, HttpResponse, HttpResponseForbidden
from django.views.decorators.csrf import csrf_exempt
from django.forms.models import model_to_dict
from django.db.models import Sum, F, Count, Q
from django.db import IntegrityError
from collections import defaultdict

from .roles import can_manage_users
from .tenant import get_active_organization, branding_template_context
from .currency import fmt_money
from .models import (
    UserAccount, UserCategory, AppSettings, Organization,
    BankAccount, SupplierAccount,
    GLAccount, GLAnalysisCategory, ProjectTask, ProjectBuildCategory,
    Product, ProjectBuilding, BOMHeader, BOMItem,
    RequisitionOrder, RequisitionOrderItem, LPOTransaction, LPOItem,
    RFQTransaction, GRNTransaction, GRNItem, PaymentOrder, MiscRequisitionOrder,
    MiscPurchaseOrder, MiscPurchaseItem,
    AdHocOfficerPaymentVoucher, AdHocOfficerPaymentVoucherLine,
    ProjectBudget, BudgetTransaction, TaskDisbursementPayment, CEOFundRelease,
    BudgetReviewEvent,
)

# ── Task resolution helpers (lines 43–184 in original views.py) ──────────────

def _clean_bracketed_text(raw, *, max_len=200):
    # line 43 — original implementation stays here
    pass  # ← PASTE original body from views.py line 43

def _normalize_task_id(raw):
    # line 65
    pass  # ← PASTE original body

def _normalize_task_description(raw):
    # line 70
    pass  # ← PASTE original body

def _resolve_project_task(qs, raw):
    # line 75
    pass  # ← PASTE original body

def _bom_task_pick_id(task):
    # line 97
    pass  # ← PASTE original body

def _task_id_from_request(request, *, include_post=False, include_session=True):
    # line 104
    pass  # ← PASTE original body

def _task_from_request(request, *, include_post=False, include_session=True, queryset=None):
    # line 114
    pass  # ← PASTE original body

def _bid_eval_active_task(request):
    # line 146
    pass  # ← PASTE original body

def _bid_eval_redirect_url(task):
    # line 165
    pass  # ← PASTE original body

def _bid_eval_sidebar_tools_enabled(workspace):
    # line 175
    pass  # ← PASTE original body

# ── Money / formatting helpers ────────────────────────────────────────────────

def _money(post, key, default="0"):
    # line 3401
    pass  # ← PASTE original body

def _print_items_count(items):
    # line 2970
    pass  # ← PASTE original body

def _redirect_empty_print(request, message, return_url):
    # line 2981
    pass  # ← PASTE original body

# ── Budget channel helpers (shared by views_misc and views_budget) ────────────

def _budget_channel_label(channel):
    # line 4414
    pass  # ← PASTE original body

def _task_budget_record(task):
    # line 4422
    pass  # ← PASTE original body

def _misc_channel_allowed(task):
    # line 4428
    pass  # ← PASTE original body

def _rfq_channel_allowed(task):
    # line 4444
    pass  # ← PASTE original body

def _save_task_budget(task, budget_type, material, labour, misc, total, label=None):
    # line 4877
    pass  # ← PASTE original body

def _build_task_budget_status(task):
    # line 3408
    pass  # ← PASTE original body

# ── Print guards (shared by procurement and misc print views) ─────────────────

def _rfq_letter_print_guard(request, context):
    # line 2986
    pass  # ← PASTE original body

def _mpo_print_guard(request, context):
    # line 3007
    pass  # ← PASTE original body

def _mro_print_guard(request, context):
    # line 3019
    pass  # ← PASTE original body

def _payment_voucher_back_url(task):
    # line 4121
    pass  # ← PASTE original body

def _build_payment_voucher_context(pv):
    # line 4130
    pass  # ← PASTE original body

# ── Cross-task activity feed (used by dashboard) ──────────────────────────────

def _ops_cross_task_activity_feed():
    # line 404
    pass  # ← PASTE original body

def _ops_task_panel_context(task):
    # line 2118
    pass  # ← PASTE original body
