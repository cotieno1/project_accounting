from django.utils import timezone
import secrets
import calendar
import re
import json
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
from django.db.models import Sum, F, Count
from django.db import IntegrityError
from collections import defaultdict

# SINGLE UNIFIED IMPORT BLOCK - All models imported exactly once
from .roles import can_manage_users
from .tenant import get_active_organization, branding_template_context
from .currency import fmt_money
from .models import (
    UserAccount, UserCategory, AppSettings, Organization,
    BankAccount, SupplierAccount,
    GLAccount, GLAnalysisCategory, ProjectTask, ProjectBuildCategory,
    Product, ProjectBuilding, BOMHeader, BOMItem,
    RequisitionOrder, RequisitionOrderItem, LPOTransaction,LPOItem,
    RFQTransaction, GRNTransaction, GRNItem, PaymentOrder, MiscRequisitionOrder,
    MiscPurchaseOrder, MiscPurchaseItem,
    AdHocOfficerPaymentVoucher, AdHocOfficerPaymentVoucherLine,
    ProjectBudget, BudgetTransaction, TaskDisbursementPayment, CEOFundRelease,
)
#=========================================================================

def _task_id_from_request(request, *, include_post=False, include_session=True):
    """Resolve task_id from URL, form POST, then last user choice in session."""
    task_id = (request.GET.get("task_id") or "").strip()
    if not task_id and include_post:
        task_id = (request.POST.get("task_id") or "").strip()
    if not task_id and include_session:
        task_id = (request.session.get("active_task_id") or "").strip()
    return task_id


def _task_from_request(request, tasks_qs=None, *, include_post=False, persist_session=True):
    """Resolve task from URL, form, session, then first task (demo default). Updates session."""
    task_id = _task_id_from_request(request, include_post=include_post)
    qs = tasks_qs if tasks_qs is not None else ProjectTask.objects.all()
    task = qs.filter(project_id=task_id).first() if task_id else None
    if task_id and not task:
        request.session.pop("active_task_id", None)
    if not task:
        task = qs.order_by("project_id").first()
    if task and persist_session:
        request.session["active_task_id"] = task.project_id
    return task


# =======================================================================
# 🔐 AUTH & ACCESS CONTROLLERS
# =======================================================================
class CustomLoginView(LoginView):
    template_name = 'login.html'
    redirect_authenticated_user = True

    @method_decorator(ensure_csrf_cookie)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    def get_success_url(self):
        from django.urls import reverse
        try:
            if self.request.user.useraccount.must_change_password:
                return reverse("password_change_required")
        except Exception:
            pass
        return super().get_success_url()

def has_module_access(user, module_code):
    from .roles import user_can, USER_ADMIN, get_role_code
    if user and user.is_superuser:
        return True
    if get_role_code(user) == USER_ADMIN:
        return True
    try:
        return user.useraccount.access_level.modules.filter(name=module_code).exists()
    except Exception:
        return False

# =======================================================================
# 🏠 NAVIGATION CORE
# =======================================================================
def home(request):
    return render(request, 'home.html')


def health(request):
    """Lightweight health check for Railway (no database)."""
    return HttpResponse('ok', content_type='text/plain')


def set_password_onboarding(request, uidb64, token):
    from django.contrib.auth.tokens import default_token_generator
    from django.utils.encoding import force_str
    from django.utils.http import urlsafe_base64_decode

    error = None
    success = None
    user = None
    user_account = None
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
        user_account = getattr(user, "useraccount", None)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        error = "This link is invalid or has expired."
        user = None

    if user and not default_token_generator.check_token(user, token):
        error = "This link is invalid or has expired."

    if request.method == "POST" and user and not error:
        password = (request.POST.get("password") or "").strip()
        password_confirm = (request.POST.get("password_confirm") or "").strip()
        pw, pw_err = _validate_user_passwords(password, password_confirm, required=True)
        if pw_err:
            error = pw_err
        else:
            user.set_password(pw)
            user.save()
            if user_account:
                user_account.must_change_password = False
                if not user_account.onboarded_at:
                    user_account.onboarded_at = timezone.now()
                user_account.save()
            success = "Password saved. You can now sign in."
            user = None

    return render(
        request,
        "set_password_onboarding.html",
        {"error": error, "success": success, "user_account": user_account},
    )


@login_required
def password_change_required(request):
    ua = getattr(request.user, "useraccount", None)
    return render(
        request,
        "password_change_required.html",
        {
            "email": ua.email if ua else request.user.email,
            "can_resend": bool(ua and ua.email),
        },
    )


@login_required
def resend_onboarding_email(request):
    from .emails import send_onboarding_email
    from .roles import can_manage_users

    if request.method != "POST":
        return HttpResponseForbidden("Method not allowed")
    ua = getattr(request.user, "useraccount", None)
    if not ua or not ua.email or not ua.must_change_password:
        messages.error(request, "Onboarding resend is not available for this account.")
        return redirect("dashboard")
    ua.must_change_password = True
    request.user.set_unusable_password()
    request.user.save()
    ua.save()
    ok, err = send_onboarding_email(ua, request=request)
    if ok:
        messages.success(request, "Onboarding email sent. Check your inbox.")
    else:
        messages.error(request, err or "Could not send email. Contact User Admin.")
    return redirect("password_change_required")


def android_rollout_plan_doc(request):
    """Simple download page for the Android rollout plan PDF."""
    return render(request, 'docs_android_rollout.html')

@login_required
def dashboard(request):
    user = request.user
    try:
        user_account = user.useraccount
        role = user_account.access_level.description
        modules = user_account.access_level.modules.all()
    except Exception:
        role = "Project Director"
        modules = []

    try:
        active_org = get_active_organization(request)
        context = {
            'username': user.username,
            'role': role,
            'modules': modules,
            'categories': UserCategory.objects.all(),
            'analysis_categories': GLAnalysisCategory.objects.all(),
            'role_options': [
                {"id": c.id, "description": c.description}
                for c in UserCategory.objects.all()
            ],
            'analysis_options': [
                {"category_id": c.category_id, "description": c.description}
                for c in GLAnalysisCategory.objects.all()
            ],
            'recon_progress': 84,
            'organization_options': [
                {
                    "org_code": o.org_code,
                    "name": o.name,
                    "short_name": o.short_name,
                }
                for o in Organization.objects.all().order_by("org_code")
            ],
            'can_switch_organization': request.user.is_superuser,
            'active_org_code': active_org.org_code if active_org else "",
            'can_manage_users': request.user.is_superuser or can_manage_users(request.user),
        }
        return render(request, 'dashboard.html', context)
    except Exception:
        return render(
            request,
            'dashboard_unavailable.html',
            {'username': user.username},
            status=503,
        )


@login_required
@csrf_exempt
def switch_active_organization(request):
    """Platform admin: preview another client company on the shared service."""
    if request.method != "POST":
        return HttpResponseForbidden("Method not allowed")
    if not request.user.is_superuser:
        return JsonResponse(
            {"status": "error", "message": "Only platform administrators can switch companies."},
            status=403,
        )
    org_code = (request.POST.get("org_code") or "").strip()
    org = Organization.objects.filter(org_code=org_code).first()
    if not org:
        return JsonResponse(
            {"status": "error", "message": "Organization not found."},
            status=400,
        )
    request.session["active_org_code"] = org_code
    return JsonResponse({
        "status": "success",
        "message": f"Now viewing as {org.name}.",
        "org_code": org_code,
    })

def _ops_cross_task_activity_feed():
    """Hard-coded cross-task activity log — Major (BOM) and Ad-Hoc (Misc) lanes."""
    return [
        {
            "ref": "TSK-101",
            "actor": "Project Dir.",
            "action": "Task Assigned: House Building",
            "project_stage": "Task Assigned",
            "financial_type": "none",
            "financial_value": "",
            "status": "Actioned",
            "status_class": "badge-primary",
        },
        {
            "ref": "BOM-042",
            "actor": "Snr Site Mgr",
            "action": "BOM Submitted: 600 Bags Cement",
            "project_stage": "BOM",
            "financial_type": "est",
            "financial_value": "12,000",
            "status": "Baselined",
            "status_class": "badge-success",
        },
        {
            "ref": "LPO-001",
            "actor": "GM / Director",
            "action": "LPO Issued to Orion Supplies",
            "project_stage": "LPO",
            "financial_type": "actual",
            "financial_value": "12,000.00",
            "status": "Authorized",
            "status_class": "badge-execution",
        },
        {
            "ref": "TSK-026",
            "actor": "Project Dir.",
            "action": "Task Assigned: Emergency Plumbing",
            "project_stage": "Task Assigned",
            "financial_type": "none",
            "financial_value": "",
            "status": "Actioned",
            "status_class": "badge-primary",
        },
        {
            "ref": "MRO-088",
            "actor": "Site Officer",
            "action": "Misc RO Submitted: Pipe Fittings & Valves",
            "project_stage": "Misc RO",
            "financial_type": "est",
            "financial_value": "450",
            "status": "Submitted",
            "status_class": "badge-planning",
        },
        {
            "ref": "MRO-088",
            "actor": "GM / Director",
            "action": "MRO Approved — Officer Payment Path",
            "project_stage": "Fund Disbursed",
            "financial_type": "actual",
            "financial_value": "450.00",
            "status": "Authorized",
            "status_class": "badge-execution",
        },
        {
            "ref": "TSK-3330",
            "actor": "Project Dir.",
            "action": "Task Assigned: Pioneer HWF Phase 2",
            "project_stage": "Budget Approval",
            "financial_type": "none",
            "financial_value": "",
            "status": "Actioned",
            "status_class": "badge-primary",
        },
        {
            "ref": "BOM-033",
            "actor": "Snr Site Mgr",
            "action": "BOM Draft: Structural Steel Items",
            "project_stage": "BOM",
            "financial_type": "est",
            "financial_value": "8,400",
            "status": "In Progress",
            "status_class": "badge-planning",
        },
    ]


@login_required
def fin_mgmt_ops_view(request):
    tasks = ProjectTask.objects.order_by("project_id")
    active_task = _task_from_request(request, tasks)
    task_panel = _ops_task_panel_context(active_task)

    context = {
        'page_title': 'Pioneer Financial Ops',
        'tasks': tasks,
        'active_task': active_task,
        'task_panel': task_panel,
        'activity_feed': _ops_cross_task_activity_feed(),
        'bom_no': task_panel["bom_display"],
        'mtd_actuals': "89,200.00",
    }
    return render(request, 'Fin_Mgmt_and_OPs_dashboard.html', context)

# =======================================================================
# 🚀 PIONEER UNIFIED TRAFFIC CONTROLLER (CRUD ENGINE)
# =======================================================================
def get_pioneer_model(entity_type):
    """Helper to map URL strings to actual Model classes from models.py"""
    model_map = {
        'user': UserAccount,
        'role': UserCategory,
        'bank': BankAccount,
        'supplier': SupplierAccount,
        'gl': GLAccount,
        'analysis': GLAnalysisCategory,
        'task': ProjectTask,
        'build': ProjectBuildCategory,
        'product': Product,
        'app_settings': AppSettings,
        'organization': Organization,
        'building': ProjectBuilding,
        'ro': RequisitionOrder,
        'ro_item': RequisitionOrderItem,
        'bom': BOMHeader,
        'bom_item': BOMItem,
        'lpo': LPOTransaction,
        'rfq': RFQTransaction,
    }
    return model_map.get(entity_type.lower())

MASTER_ENTITY_META = {
    "user": {
        "title": "User Accounts",
        "columns": [
            ("staff_no", "Staff No"),
            ("username", "Login Username"),
            ("first_name", "First Name"),
            ("last_name", "Last Name"),
            ("designation", "Designation"),
            ("email", "Email"),
            ("phone", "Phone"),
            ("organization", "Company"),
            ("role", "Role"),
            ("onboarding_status", "Onboarding"),
            ("invite_sent_at", "Invite Email Sent"),
            ("password_set_at", "Password Set"),
        ],
    },
    "role": {
        "title": "User Categories (Roles)",
        "columns": [("id", "ID"), ("description", "Description")],
    },
    "bank": {
        "title": "Bank Accounts",
        "columns": [
            ("bank_account_id", "Bank ID"),
            ("account_number", "Account No"),
            ("description", "Bank Name"),
            ("phone", "Phone"),
            ("email", "Email"),
        ],
    },
    "supplier": {
        "title": "Supplier Accounts",
        "columns": [
            ("supplier_id", "Supplier ID"),
            ("description", "Name"),
            ("phone", "Phone"),
            ("email", "Email"),
            ("bank_account_number", "Bank A/C"),
        ],
    },
    "gl": {
        "title": "GL Accounts",
        "columns": [
            ("gl_account_id", "GL Code"),
            ("description", "Name"),
            ("debit_credit", "Dr/Cr"),
            ("analysis_category", "Analysis"),
            ("currency", "Currency"),
            ("amount", "Amount"),
        ],
    },
    "analysis": {
        "title": "GL Analysis Codes",
        "columns": [("category_id", "Code"), ("description", "Description")],
    },
    "task": {
        "title": "Project Tasks",
        "columns": [("project_id", "Task ID"), ("description", "Description")],
    },
    "build": {
        "title": "Project Build Categories",
        "columns": [("build_cat_id", "Category ID"), ("description", "Description")],
    },
    "product": {
        "title": "Product Items",
        "columns": [
            ("product_id", "Product ID"),
            ("description", "Description"),
            ("unit_of_measure", "UOM"),
            ("stock_quantity", "Stock"),
        ],
    },
    "app_settings": {
        "title": "Software Setup",
        "columns": [
            ("app_name", "Software Name"),
            ("app_short_name", "Short Name"),
            ("app_tagline", "Tagline"),
            ("support_email", "Support Email"),
            ("currency_code", "Currency Code"),
            ("currency_symbol", "Currency Symbol"),
        ],
    },
    "organization": {
        "title": "Client Organizations",
        "columns": [
            ("org_code", "Code"),
            ("name", "Company Name"),
            ("contact_address", "Contact Address"),
            ("phone", "Phone"),
            ("email", "Email"),
            ("is_default", "Default"),
        ],
    },
}


def _entity_pk_value(obj):
    return str(obj.pk)


def _format_master_datetime(dt):
    if not dt:
        return "—"
    return dt.strftime("%d %b %Y %H:%M")


def _user_onboarding_api_fields(ua):
    """Onboarding columns for Command Center user list and edit form."""
    return {
        "onboarding_status": ua.onboarding_status_label(),
        "invite_sent_at": (
            _format_master_datetime(ua.onboarding_email_sent_at)
            if ua.onboarding_email_sent_at
            else ("Failed" if ua.onboarding_email_last_error else "Not sent")
        ),
        "invite_last_error": ua.onboarding_email_last_error or "",
        "password_set_at": (
            _format_master_datetime(ua.onboarded_at)
            if ua.onboarded_at and not ua.must_change_password
            else "—"
        ),
        "can_resend_onboarding": bool(
            ua.email and ua.user and ua.must_change_password
        ),
    }


def _serialize_master_row(entity_type, obj):
    row = {"_pk": _entity_pk_value(obj)}
    if entity_type == "user":
        row.update({
            "staff_no": obj.staff_no,
            "username": obj.user.username if obj.user else "—",
            "first_name": obj.first_name,
            "last_name": obj.last_name,
            "designation": obj.designation,
            "email": obj.email,
            "phone": obj.phone,
            "organization": (
                obj.organization.short_name if obj.organization else "—"
            ),
            "role": obj.access_level.description if obj.access_level else "—",
            **_user_onboarding_api_fields(obj),
        })
    elif entity_type == "role":
        row.update({"id": obj.id, "description": obj.description})
    elif entity_type == "bank":
        row.update({
            "bank_account_id": obj.bank_account_id,
            "account_number": obj.account_number,
            "description": obj.description,
            "phone": obj.phone,
            "email": obj.email,
        })
    elif entity_type == "supplier":
        row.update({
            "supplier_id": obj.supplier_id,
            "description": obj.description,
            "phone": obj.phone,
            "email": obj.email,
            "bank_account_number": obj.bank_account_number,
        })
    elif entity_type == "gl":
        row.update({
            "gl_account_id": obj.gl_account_id,
            "description": obj.description,
            "debit_credit": obj.debit_credit,
            "analysis_category": (
                obj.analysis_category.description if obj.analysis_category else "—"
            ),
            "currency": obj.currency,
            "amount": str(obj.amount),
        })
    elif entity_type == "analysis":
        row.update({"category_id": obj.category_id, "description": obj.description})
    elif entity_type == "task":
        row.update({"project_id": obj.project_id, "description": obj.description})
    elif entity_type == "build":
        row.update({"build_cat_id": obj.build_cat_id, "description": obj.description})
    elif entity_type == "product":
        row.update({
            "product_id": obj.product_id,
            "description": obj.description,
            "unit_of_measure": obj.unit_of_measure,
            "stock_quantity": obj.stock_quantity,
        })
    elif entity_type == "app_settings":
        row.update({
            "app_name": obj.app_name,
            "app_short_name": obj.app_short_name,
            "app_tagline": obj.app_tagline,
            "support_email": obj.support_email,
            "currency_code": obj.currency_code,
            "currency_symbol": obj.currency_symbol,
        })
    elif entity_type == "organization":
        addr = (obj.contact_address or obj.registered_address or "—").replace("\n", ", ")
        if len(addr) > 60:
            addr = addr[:57] + "..."
        row.update({
            "org_code": obj.org_code,
            "name": obj.name,
            "short_name": obj.short_name,
            "contact_address": addr,
            "phone": obj.phone or "—",
            "email": obj.email or "—",
            "is_default": "Yes" if obj.is_default else "—",
        })
    return row


def _normalize_org_code(raw):
    """Strip accidental JSON/list wrappers from master-registry input."""
    code = (raw or "").strip()
    if code.startswith("[") and code.endswith("]"):
        inner = code[1:-1].strip().strip("'\"")
        if inner:
            code = inner
    return code.strip("[]'\" ").upper()


def _validate_organization_payload(data):
    org_code = _normalize_org_code(data.get("org_code"))
    name = (data.get("name") or "").strip()
    if name.startswith("[") and name.endswith("]"):
        name = name[1:-1].strip().strip("'\"")
    if not org_code:
        return None, "Organization code is required (e.g. PIONEER)."
    if not re.match(r"^[A-Z0-9][A-Z0-9_-]{0,28}$", org_code):
        return None, (
            "Organization code must be 1–30 characters: letters, numbers, underscore, hyphen."
        )
    if not name:
        return None, "Company name is required."
    cleaned = dict(data)
    cleaned["org_code"] = org_code
    cleaned["name"] = name
    if cleaned.get("short_name"):
        cleaned["short_name"] = cleaned["short_name"].strip()
    return cleaned, None


def _apply_entity_payload(model, data, entity_type):
    """Map POST fields to model kwargs, resolving FK ids."""
    cleaned = {
        k: v for k, v in data.items()
        if k not in ("mode", "original_id", "csrfmiddlewaretoken", "username", "password")
        and v is not None and str(v).strip() != ""
    }
    if entity_type == "user":
        return cleaned
    if entity_type == "organization":
        cleaned["is_default"] = str(data.get("is_default", "")).lower() in (
            "1", "true", "on", "yes"
        )
    if entity_type == "gl" and cleaned.get("analysis_category"):
        cat = GLAnalysisCategory.objects.filter(
            category_id=cleaned["analysis_category"]
        ).first() or GLAnalysisCategory.objects.filter(
            pk=cleaned["analysis_category"]
        ).first()
        if cat:
            cleaned["analysis_category"] = cat
        else:
            cleaned.pop("analysis_category", None)
    if entity_type == "gl" and cleaned.get("amount"):
        cleaned["amount"] = Decimal(str(cleaned["amount"]))
    if entity_type == "product" and cleaned.get("stock_quantity"):
        cleaned["stock_quantity"] = int(cleaned["stock_quantity"])
    return cleaned


@login_required
@csrf_exempt
def unified_api_create(request, entity_type):
    """Handles Save/Update for master-data models via AJAX."""
    if request.method != "POST":
        return HttpResponseForbidden("Method not allowed")

    entity_type = (entity_type or "").lower()
    if entity_type == "user":
        return create_user(request)

    if entity_type == "app_settings":
        try:
            app = AppSettings.get()
            app.app_name = request.POST.get("app_name", app.app_name).strip()
            app.app_short_name = request.POST.get(
                "app_short_name", app.app_short_name
            ).strip()
            app.app_tagline = request.POST.get("app_tagline", app.app_tagline).strip()
            app.support_email = request.POST.get(
                "support_email", app.support_email
            ).strip()
            app.vendor_name = request.POST.get("vendor_name", app.vendor_name).strip()
            app.currency_code = request.POST.get(
                "currency_code", app.currency_code
            ).strip() or "USD"
            app.currency_symbol = request.POST.get(
                "currency_symbol", app.currency_symbol
            ).strip() or "US$"
            app.save()
            return JsonResponse({
                "status": "success",
                "message": "Software setup saved.",
            })
        except Exception as e:
            return JsonResponse({"status": "error", "message": str(e)}, status=400)

    model = get_pioneer_model(entity_type)
    if not model:
        return JsonResponse({"status": "error", "message": "Invalid entity"}, status=400)

    mode = request.POST.get("mode", "create")
    original_id = (request.POST.get("original_id") or "").strip()
    if entity_type == "organization":
        if not (request.POST.get("name") or "").strip():
            return JsonResponse(
                {"status": "error", "message": "Company name is required."},
                status=400,
            )
        if not (request.POST.get("contact_address") or "").strip():
            return JsonResponse(
                {"status": "error", "message": "Contact / office address is required."},
                status=400,
            )
        validated, err = _validate_organization_payload(dict(request.POST))
        if err:
            return JsonResponse({"status": "error", "message": err}, status=400)
        if mode == "edit" and original_id:
            validated.pop("org_code", None)
        data = _apply_entity_payload(model, validated, entity_type)
    else:
        data = _apply_entity_payload(model, dict(request.POST), entity_type)

    try:
        if mode == "edit" and original_id:
            obj = get_object_or_404(model, pk=original_id)
            for key, value in data.items():
                if hasattr(obj, key):
                    setattr(obj, key, value)
            obj.save()
            msg = f"{MASTER_ENTITY_META.get(entity_type, {}).get('title', entity_type)} updated."
        else:
            model.objects.create(**data)
            msg = f"{MASTER_ENTITY_META.get(entity_type, {}).get('title', entity_type)} created."
        return JsonResponse({"status": "success", "message": msg})
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=500)


@login_required
def get_entity_list(request, entity_type):
    """List master records with stable primary keys for edit/delete."""
    entity_type = (entity_type or "").lower()
    model = get_pioneer_model(entity_type)
    if not model:
        return JsonResponse({"status": "error", "message": "Invalid entity"}, status=400)

    meta = MASTER_ENTITY_META.get(entity_type, {"title": entity_type.title(), "columns": []})
    if entity_type == "app_settings":
        data = [_serialize_master_row(entity_type, AppSettings.get())]
        return JsonResponse({
            "status": "success",
            "entity": entity_type,
            "title": meta["title"],
            "columns": meta["columns"],
            "data": data,
        })
    if entity_type == "user":
        qs = UserAccount.objects.select_related(
            "access_level", "organization"
        ).all().order_by("-id")
    elif entity_type == "gl":
        qs = GLAccount.objects.select_related("analysis_category").all().order_by("gl_account_id")
    else:
        qs = model.objects.all().order_by(model._meta.pk.name)

    data = [_serialize_master_row(entity_type, obj) for obj in qs]
    return JsonResponse({
        "status": "success",
        "entity": entity_type,
        "title": meta["title"],
        "columns": meta["columns"],
        "data": data,
    })


@login_required
def get_entity_detail(request, entity_type, pk):
    """Pull one record to pre-fill edit forms."""
    entity_type = (entity_type or "").lower()
    if entity_type == "app_settings":
        app = AppSettings.get()
        return JsonResponse({
            "status": "success",
            "data": model_to_dict(app),
        })
    if entity_type == "user":
        ua = get_object_or_404(
            UserAccount.objects.select_related("access_level", "organization"), pk=pk
        )
        return JsonResponse({
            "status": "success",
            "data": {
                "staff_no": ua.staff_no,
                "first_name": ua.first_name,
                "last_name": ua.last_name,
                "designation": ua.designation,
                "phone": ua.phone,
                "email": ua.email,
                "contact_address": ua.contact_address,
                "access_level_id": ua.access_level_id or "",
                "organization_id": ua.organization_id or "",
                "username": ua.user.username if ua.user else "",
                **_user_onboarding_api_fields(ua),
            },
        })

    model = get_pioneer_model(entity_type)
    obj = get_object_or_404(model, pk=pk)
    payload = model_to_dict(obj)
    if entity_type == "gl" and obj.analysis_category_id:
        payload["analysis_category"] = obj.analysis_category.category_id
    return JsonResponse({"status": "success", "data": payload})


@login_required
@csrf_exempt
def delete_entity(request, entity_type, pk):
    """Delete a master-data record."""
    entity_type = (entity_type or "").lower()
    if entity_type == "app_settings":
        return JsonResponse(
            {"status": "error", "message": "Software setup cannot be deleted."},
            status=400,
        )
    if entity_type == "user":
        ua = get_object_or_404(UserAccount, pk=pk)
        if ua.user:
            ua.user.delete()
        else:
            ua.delete()
        return JsonResponse({"status": "success", "message": "User account deleted."})
    if entity_type == "organization":
        org = get_object_or_404(Organization, pk=pk)
        if Organization.objects.count() <= 1:
            return JsonResponse(
                {"status": "error", "message": "At least one organization is required."},
                status=400,
            )
        was_default = org.is_default
        org.delete()
        if was_default:
            first = Organization.objects.first()
            if first:
                first.is_default = True
                first.save()
        return JsonResponse({"status": "success", "message": "Organization deleted."})

    model = get_pioneer_model(entity_type)
    if not model:
        return JsonResponse({"status": "error", "message": "Invalid entity"}, status=400)

    try:
        instance = get_object_or_404(model, pk=pk)
        instance.delete()
        return JsonResponse({"status": "success", "message": f"Record {pk} deleted."})
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=500)


def _validate_user_passwords(password, password_confirm, required=True):
    password = (password or "").strip()
    password_confirm = (password_confirm or "").strip()
    if not password:
        if required:
            return None, "Login password is required for new users."
        return None, None
    if len(password) < 8:
        return None, "Password must be at least 8 characters."
    if password != password_confirm:
        return None, "Password and confirmation do not match."
    return password, None


def _ensure_useraccount_login(ua, *, username, email, first_name, last_name):
    """Create or refresh the Django login linked to a UserAccount."""
    username = (username or "").strip() or (ua.staff_no or "").strip()
    if not username and email:
        username = email.split("@")[0].strip()
    if not username:
        raise ValueError("Login username is required.")

    if ua.user_id:
        user = ua.user
        conflict = User.objects.filter(username=username).exclude(pk=user.pk).exists()
        if conflict:
            raise ValueError(f"Username '{username}' is already taken.")
        user.username = username
        if email:
            user.email = email
        if first_name:
            user.first_name = first_name
        if last_name:
            user.last_name = last_name
        user.save()
        return user

    if User.objects.filter(username=username).exists():
        raise ValueError(f"Username '{username}' is already taken.")

    user = User.objects.create_user(
        username=username,
        email=email or ua.email,
        password=secrets.token_urlsafe(32),
        first_name=first_name or ua.first_name,
        last_name=last_name or ua.last_name,
    )
    user.set_unusable_password()
    user.save()
    ua.user = user
    ua.must_change_password = True
    ua.save(update_fields=["user", "must_change_password"])
    return user


def _send_user_onboarding_invite(ua, request, invited_by):
    from .emails import send_onboarding_email

    if not ua.email:
        raise ValueError("User has no email address.")
    _ensure_useraccount_login(
        ua,
        username=ua.user.username if ua.user else ua.staff_no,
        email=ua.email,
        first_name=ua.first_name,
        last_name=ua.last_name,
    )
    ua.must_change_password = True
    ua.onboarded_at = None
    ua.user.set_unusable_password()
    ua.user.save()
    ua.save(update_fields=["must_change_password", "onboarded_at"])
    ok, err = send_onboarding_email(ua, request=request, invited_by=invited_by)
    if ok:
        return True
    raise ValueError(err or "Could not send email. Check SMTP settings.")


@login_required
def create_user(request):
    from .emails import send_onboarding_email
    from .roles import can_manage_users

    if request.method != "POST":
        return HttpResponseForbidden("Method not allowed")

    if not can_manage_users(request.user):
        return JsonResponse(
            {"status": "error", "message": "Only User Admin can create or edit user accounts."},
            status=403,
        )

    mode = request.POST.get("mode", "create")
    original_id = (request.POST.get("original_id") or "").strip()
    staff_no = (request.POST.get("staff_no") or "").strip()
    first_name = request.POST.get("first_name", "")
    last_name = request.POST.get("last_name", "")
    username = (request.POST.get("username") or "").strip()
    email = request.POST.get("email", "")
    password = request.POST.get("password", "")
    password_confirm = request.POST.get("password_confirm", "")
    cat_id = request.POST.get("access_level_id")
    category = UserCategory.objects.filter(id=cat_id).first() if cat_id else None
    org_code = (request.POST.get("organization_id") or "").strip()
    organization = (
        Organization.objects.filter(org_code=org_code).first() if org_code else None
    )

    try:
        if mode == "edit" and original_id:
            ua = get_object_or_404(UserAccount, pk=original_id)

            if request.POST.get("resend_onboarding") == "1":
                try:
                    _send_user_onboarding_invite(ua, request, request.user)
                    return JsonResponse({
                        "status": "success",
                        "message": f"Invite email sent to {ua.email}.",
                    })
                except ValueError as exc:
                    return JsonResponse({"status": "error", "message": str(exc)}, status=400)

            ua.staff_no = staff_no or ua.staff_no
            ua.first_name = first_name
            ua.last_name = last_name
            ua.designation = request.POST.get("designation", ua.designation)
            ua.phone = request.POST.get("phone", ua.phone)
            ua.email = email or ua.email
            ua.contact_address = request.POST.get("contact_address", ua.contact_address)
            ua.access_level = category
            if org_code:
                ua.organization = organization
            ua.save()

            if username or not ua.user_id:
                _ensure_useraccount_login(
                    ua,
                    username=username,
                    email=email or ua.email,
                    first_name=first_name,
                    last_name=last_name,
                )

            if ua.user:
                if email:
                    ua.user.email = email
                if first_name:
                    ua.user.first_name = first_name
                if last_name:
                    ua.user.last_name = last_name
                pw, pw_err = _validate_user_passwords(
                    password, password_confirm, required=False
                )
                if pw_err:
                    return JsonResponse({"status": "error", "message": pw_err}, status=400)
                if pw:
                    ua.user.set_password(pw)
                    ua.must_change_password = False
                    if not ua.onboarded_at:
                        ua.onboarded_at = timezone.now()
                ua.user.save()
            ua.save()
            send_invite = request.POST.get("send_onboarding") == "1"
            invite_sent = False
            if send_invite and ua.email and not (password or "").strip():
                try:
                    _send_user_onboarding_invite(ua, request, request.user)
                    invite_sent = True
                except ValueError as exc:
                    return JsonResponse({"status": "error", "message": str(exc)}, status=400)
            return JsonResponse({
                "status": "success",
                "message": "User account updated."
                + (" Login password changed." if (password or "").strip() else "")
                + (f" Invite email sent to {ua.email}." if invite_sent else ""),
            })

        send_invite = request.POST.get("send_onboarding") == "1"
        if not username:
            username = staff_no or (email.split("@")[0] if email else None)
        if not username:
            return JsonResponse(
                {"status": "error", "message": "Login username is required."},
                status=400,
            )

        if not email:
            return JsonResponse(
                {"status": "error", "message": "Email is required for onboarding."},
                status=400,
            )

        if send_invite:
            pw, pw_err = _validate_user_passwords(
                password, password_confirm, required=False
            )
            if pw_err:
                return JsonResponse({"status": "error", "message": pw_err}, status=400)
            if not pw and not getattr(settings, "EMAIL_CONFIGURED", False):
                return JsonResponse(
                    {
                        "status": "error",
                        "message": (
                            "Platform email is not configured yet. Uncheck Send invite email "
                            "and enter a login password (min. 8 characters), or add RESEND_API_KEY "
                            "on Railway first."
                        ),
                    },
                    status=400,
                )

        if User.objects.filter(username=username).exists():
            return JsonResponse(
                {"status": "error", "message": f"Username '{username}' is already taken."},
                status=400,
            )

        user = User.objects.create_user(
            username=username,
            email=email,
            password=secrets.token_urlsafe(32),
            first_name=first_name,
            last_name=last_name,
        )
        user.set_unusable_password()
        user.save()

        if not organization:
            organization = get_active_organization(request) or Organization.get_default()

        admin_ua = getattr(request.user, "useraccount", None)
        ua = UserAccount.objects.create(
            user=user,
            staff_no=staff_no or username,
            first_name=first_name,
            last_name=last_name,
            designation=request.POST.get("designation", ""),
            phone=request.POST.get("phone", ""),
            email=email,
            contact_address=request.POST.get("contact_address", ""),
            access_level=category,
            organization=organization,
            must_change_password=send_invite,
            onboarded_by=admin_ua,
        )
        if send_invite:
            pw, pw_err = _validate_user_passwords(password, password_confirm, required=False)
            if pw_err:
                return JsonResponse({"status": "error", "message": pw_err}, status=400)
            if pw:
                user.set_password(pw)
                user.save()
                ua.must_change_password = False
                ua.onboarded_at = timezone.now()
                ua.save(update_fields=["must_change_password", "onboarded_at"])
                emailed = False
                msg_extra = " User can log in with the admin password you set."
            else:
                ok, err = send_onboarding_email(ua, request=request, invited_by=request.user)
                msg_extra = (
                    "Onboarding email sent — user must set password via the link."
                    if ok
                    else f"User created but email could not be sent: {err or 'check EMAIL settings.'}"
                )
        else:
            pw, pw_err = _validate_user_passwords(password, password_confirm, required=True)
            if pw_err:
                user.delete()
                return JsonResponse({"status": "error", "message": pw_err}, status=400)
            user.set_password(pw)
            user.save()
            ua.must_change_password = False
            ua.onboarded_at = timezone.now()
            ua.save(update_fields=["must_change_password", "onboarded_at"])
            emailed = False
            msg_extra = " User can log in with the password you set."
        return JsonResponse({
            "status": "success",
            "message": f"User {username} created.{msg_extra}",
        })
    except IntegrityError as e:
        err = str(e).lower()
        if "staff_no" in err or "accounts_useraccount_staff_no" in err:
            return JsonResponse(
                {
                    "status": "error",
                    "message": f"Staff number '{staff_no}' is already in use.",
                },
                status=400,
            )
        if "username" in err or "auth_user_username" in err:
            return JsonResponse(
                {
                    "status": "error",
                    "message": f"Username '{username}' is already taken.",
                },
                status=400,
            )
        return JsonResponse({"status": "error", "message": str(e)}, status=400)
    except ValueError as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=400)
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=400)

@login_required
def supplier_lookup(request):
    """Natively matches your jQuery/Vanilla JS type-ahead autocomplete structure."""
    term = request.GET.get('term', '')
    
    if len(term) >= 2:
        suppliers = SupplierAccount.objects.filter(
            description__icontains=term
        )[:10]
        
        results = [
            {'id': s.supplier_id, 'value': s.description} 
            for s in suppliers
        ]
        return JsonResponse(results, safe=False)
        
    return JsonResponse([], safe=False)

# =======================================================================
# 📝 REQUISITION ORDER (RO) & STRATEGIC BOM ENGINES
# =======================================================================
def generate_ro_no():
    last = RequisitionOrder.objects.all().order_by('id').last()
    if not last or not last.ro_no:
        return "RO No. 001"
    match = re.search(r'(\d+)', last.ro_no)
    if match:
        next_num = int(match.group(1)) + 1
        return f"RO No. {str(next_num).zfill(3)}"
    return "RO No. 001"

@login_required
def ro_builder(request):
    """Unified single logic block called securely from urls.py line 44."""
    tasks = ProjectTask.objects.all()
    active_task = _task_from_request(request, tasks)

    if not active_task:
        return render(request, "RO_builder.html", {
            "tasks": tasks,
            "active_task": None,
            "ro": None,
            "ro_no": "",
            "ro_items": [],
            "setup_message": (
                "Select a project task above to open or create its requisition order."
                if tasks.exists()
                else "Add a project task from Dashboard setup, then return here."
            ),
        })

    ro = RequisitionOrder.objects.filter(task=active_task, status="DRAFT").first()
    if not ro:
        ro = RequisitionOrder.objects.create(
            task=active_task,
            ro_no=generate_ro_no(),
            status="DRAFT"
        )

    if request.method == "POST" and "add_item" in request.POST:
        RequisitionOrderItem.objects.create(
            ro=ro,
            quantity=request.POST.get("qty"),
            uom=request.POST.get("uom", "Pcs"),
            tech_spec_summary=request.POST.get("description")
        )
        return redirect(f"/ro-builder/?task_id={active_task.project_id}")

    return render(request, "RO_builder.html", {
        "tasks": tasks,
        "active_task": active_task,
        "ro": ro,
        "ro_no": ro.ro_no,
        "ro_items": ro.items.all().order_by("id"),
    })

@login_required
def fetch_bom_to_ro(request, ro_id):
    ro = get_object_or_404(RequisitionOrder, id=ro_id)
    bom = BOMHeader.objects.filter(task=ro.task).first()
    
    if bom:
        for item in bom.items.all():
            RequisitionOrderItem.objects.get_or_create(
                ro=ro,
                tech_spec_summary=item.description,
                defaults={
                    'quantity': item.qty,
                    'uom': item.uom
                }
            )
    return redirect(f"/ro-builder/?task_id={ro.task.project_id}")


def _mpo_ro_locked(mpo):
    """True once the officer locks the Misc RO grand total (Misc RO number issued)."""
    if not mpo:
        return False
    if mpo.funding_status in ("SUBMITTED", "LOCKED", "DISBURSED"):
        return True
    return not mpo.is_sourcing


def _mpo_has_ro_number(mpo):
    """Misc RO number exists only after the grand total is locked."""
    if not mpo:
        return False
    return bool((mpo.mpo_number or "").strip()) and _mpo_ro_locked(mpo)


def _assert_mpo_editable(mpo):
    if _mpo_ro_locked(mpo):
        ref = (mpo.mpo_number or "").strip() or "Misc RO"
        raise ValueError(
            f"{ref} is locked - view only. Add, amend, delete, and supplier changes are not allowed."
        )


def _misc_display_mro_number(mro):
    """MRO number only after budget baseline is committed (locked MRO)."""
    if not mro or not (mro.mro_number or "").strip():
        return ""
    if mro.funding_status in ("LOCKED", "DISBURSED", "RECONCILED"):
        return mro.mro_number
    return ""


def _misc_display_ro_number(mpo):
    if not _mpo_has_ro_number(mpo):
        return ""
    return (mpo.mpo_number or "").strip()


def _misc_stage_b_onboarding_visible(
    task,
    *,
    ro_mode,
    batch_item_count,
    ro_locked,
    task_has_baseline,
):
    """
    Stage B MRO onboarding only (e.g. HWF-0029 empty ad-hoc).

    Hidden when the task already has MRO baseline work or the officer has
    added Misc RO lines — do not overlay this on a working MRO screen.
    """
    if not task or not _misc_channel_allowed(task)[0]:
        return False
    if task_has_baseline:
        return False
    if ro_mode == "empty":
        return True
    if ro_mode == "draft" and batch_item_count == 0 and not ro_locked:
        return True
    return False


def _prune_empty_numbered_draft_mpos(task):
    """Remove blank RO rows that were numbered before any lines were added."""
    if not task:
        return
    MiscPurchaseOrder.objects.filter(
        task=task,
        funding_status="PENDING",
        is_sourcing=True,
    ).annotate(item_count=Count("items")).filter(
        item_count=0,
    ).exclude(mpo_number__isnull=True).exclude(mpo_number="").delete()


def _require_draft_mpo(task, supplier_name=""):
    """Open PENDING MPO for this task — must already exist (via + Start RO)."""
    allowed, reason = _misc_channel_allowed(task)
    if not allowed:
        raise ValueError(reason)

    mpo = _get_active_draft_mpo(task)
    if not mpo:
        raise ValueError(
            "No open requisition on this task. Click + Start RO before adding lines or suppliers."
        )
    if supplier_name:
        mpo.messenger_name = supplier_name[:100]
        mpo.save(update_fields=["messenger_name"])
    return mpo


def _misc_purchase_tasks():
    """Tasks eligible for ad-hoc MRO â€” excludes major/BOM-lane tasks."""
    ids = [
        t.pk
        for t in ProjectTask.objects.order_by("project_id")
        if _misc_channel_allowed(t)[0]
    ]
    return ProjectTask.objects.filter(pk__in=ids).order_by("project_id")


def _task_on_major_bom_lane(task):
    """True when BOM (Y) lane is active â€” hide from ad-hoc MRO unless real MRO work exists."""
    if not task:
        return False
    if not BOMItem.objects.filter(header__task=task).exists():
        return False
    budget = _task_budget_record(task)
    if budget and budget.budget_type == ProjectBudget.BUDGET_ADHOC_MISC:
        return False
    if MiscRequisitionOrder.objects.filter(task=task).exists():
        return False
    if MiscPurchaseItem.objects.filter(task=task).exists():
        return False
    if MiscPurchaseOrder.objects.filter(
        task=task,
        funding_status__in=["SUBMITTED", "LOCKED", "DISBURSED"],
    ).exists():
        return False
    return True


def _resolve_misc_purchase_task(request, *, include_post=False):
    """Resolve active task for misc/MRO pages within the ad-hoc task list only."""
    tasks = _misc_purchase_tasks()
    requested = _task_id_from_request(request, include_post=include_post)
    if requested:
        task = tasks.filter(project_id=requested).first()
        if not task:
            if ProjectTask.objects.filter(project_id=requested).exists():
                messages.error(
                    request,
                    "That task is not on the MRO path. "
                    "Choose an MRO task from the list, or return to the main menu.",
                )
            return tasks, None
        request.session["active_task_id"] = task.project_id
        return tasks, task
    task = tasks.order_by("project_id").first()
    if task:
        request.session["active_task_id"] = task.project_id
    return tasks, task


def _task_has_misc_po_path(task):
    if not task:
        return False
    if MiscPurchaseOrder.objects.filter(task=task).exists():
        return True
    if MiscRequisitionOrder.objects.filter(task=task).exists():
        return True
    return False


def _task_on_major_procurement_lane(task):
    """Task already past fresh BOM start (budget, RO lines, RFQ, LPO, submitted BOM)."""
    if not task:
        return False
    if LPOTransaction.objects.filter(project_task=task).exists():
        return True
    if RFQTransaction.objects.filter(bom_item__project_task=task).exists():
        return True
    if RequisitionOrderItem.objects.filter(ro__task=task).exists():
        return True
    budget = _task_budget_record(task)
    if budget and budget.budget_type == ProjectBudget.BUDGET_RFQ_LPO:
        if budget.is_ceo_approved or (budget.total_authorized_budget or 0) > 0:
            return True
    if BOMHeader.objects.filter(task=task).exclude(status=BOMHeader.STATUS_DRAFT).exists():
        return True
    return False


def _task_is_new_for_bom(task):
    if not task:
        return False
    if _task_has_misc_po_path(task) or _task_on_major_procurement_lane(task):
        return False
    bom = BOMHeader.objects.filter(task=task).first()
    if not bom:
        return True
    if bom.status != BOMHeader.STATUS_DRAFT:
        return False
    return not bom.items.exists() and not bom.items_locked


def _task_bom_draft_in_progress(task):
    bom = _get_task_bom(task)
    return bool(
        bom
        and bom.status == BOMHeader.STATUS_DRAFT
        and (bom.items.exists() or bom.items_locked)
    )


def _bom_can_start_bom(task):
    """Start BOM only on fresh major-lane tasks (not misc, not past create stage)."""
    if not task or _bom_screen_lane(task) != "bom":
        return False
    bom = _get_task_bom(task)
    if not bom:
        return True
    if bom.status != BOMHeader.STATUS_DRAFT:
        return False
    return not bom.items.exists() and not bom.items_locked


def _bom_task_sidebar_hint(task):
    """Short status for BOM builder task picker."""
    if not task:
        return ""
    if _task_has_misc_po_path(task):
        mro = (
            MiscRequisitionOrder.objects.filter(task=task)
            .order_by("-updated_at")
            .first()
        )
        if mro and mro.funding_status in ("LOCKED", "DISBURSED", "RECONCILED"):
            ref = mro.mro_number or "MRO"
            return f"Misc · {ref}"
        mpo = MiscPurchaseOrder.objects.filter(task=task).order_by("-created_at").first()
        if mpo:
            return f"Misc · {mpo.get_funding_status_display()}"
        return "Misc · Ad-hoc"
    lpos = list(
        LPOTransaction.objects.filter(project_task=task).exclude(
            status=LPOTransaction.STATUS_CANCELLED
        )
    )
    if lpos:
        if all(_lpo_receipt_status(lpo) == "FULL" for lpo in lpos):
            return "Major · Delivered"
        if any(_lpo_receipt_status(lpo) in ("PARTIAL", "FULL") for lpo in lpos):
            return "Major · GRN"
        return "Major · LPO"
    if RFQTransaction.objects.filter(bom_item__project_task=task).exists():
        return "Major · RFQ"
    if RequisitionOrderItem.objects.filter(ro__task=task).exists():
        ro = RequisitionOrder.objects.filter(task=task).order_by("-date_raised").first()
        return f"Major · RO {ro.ro_no}" if ro else "Major · RO"
    bom = BOMHeader.objects.filter(task=task).first()
    if bom and bom.status != BOMHeader.STATUS_DRAFT:
        return f"BOM · {bom.get_status_display()}"
    if bom and bom.items_locked:
        return "BOM · Locked"
    if bom and bom.items.exists():
        return "BOM · Draft"
    budget = _task_budget_record(task)
    if budget and budget.budget_type == ProjectBudget.BUDGET_RFQ_LPO:
        if budget.is_ceo_approved:
            return "Major · Budget approved"
        return "Major · Budget"
    return "New · Start BOM"


def _bom_builder_task_rows():
    """All tasks with lane hint — John can scan status from one picker."""
    rows = []
    for task in ProjectTask.objects.order_by("project_id"):
        rows.append(
            {
                "task": task,
                "hint": _bom_task_sidebar_hint(task),
                "lane": _bom_screen_lane(task),
            }
        )
    return rows


def _bom_task_status_snapshot(task):
    """Read-only procurement snapshot for BOM builder (misc + major lanes)."""
    from django.urls import reverse

    lane = _bom_screen_lane(task)
    snap = {
        "lane": lane,
        "can_create_bom": _bom_can_start_bom(task),
        "stage_label": "",
        "summary_lines": [],
        "bom": None,
        "bom_items": [],
        "misc_rows": [],
        "ros": [],
        "rfqs": [],
        "lpos": [],
        "delivery_summary": "",
        "budget_label": "",
        "links": [],
    }
    if not task:
        return snap

    budget = _task_budget_record(task)
    if budget:
        snap["budget_label"] = (
            f"{_budget_channel_label(budget.budget_type)}"
            f"{' · CEO approved' if budget.is_ceo_approved else ''}"
        )
        if budget.total_authorized_budget:
            snap["summary_lines"].append(
                {
                    "label": "Authorized budget",
                    "value": f"{budget.total_authorized_budget:,.2f}",
                }
            )

    if lane == "misc":
        snap["stage_label"] = "Misc PO / MRO — cannot be processed as BOM"
        snap["summary_lines"].append(
            {"label": "Lane", "value": "Ad-hoc Misc Purchase (Lane X)"}
        )
        snap["misc_rows"] = _misc_task_mro_registry(task)
        baseline = _get_task_baseline_mpo(task)
        if baseline:
            snap["summary_lines"].append(
                {
                    "label": "Misc RO",
                    "value": _misc_display_ro_number(baseline) or "Draft",
                }
            )
            committed = getattr(baseline, "committed_mro", None)
            if committed:
                mro_ref = _misc_display_mro_number(committed) or committed.mro_number or "—"
                snap["summary_lines"].append({"label": "MRO", "value": mro_ref})
                snap["summary_lines"].append(
                    {
                        "label": "MRO status",
                        "value": committed.get_funding_status_display(),
                    }
                )
        snap["links"].append(
            {
                "label": "Open Misc Purchase",
                "url": reverse("misc_purchase_builder")
                + f"?task_id={task.project_id}",
                "primary": True,
            }
        )
        return snap

    bom = _get_task_bom(task)
    if bom:
        snap["bom"] = {
            "bom_id": bom.bom_id,
            "status": bom.get_status_display(),
            "status_code": bom.status,
            "items_locked": bom.items_locked,
            "item_count": bom.items.count(),
        }
        snap["bom_items"] = list(bom.items.all().order_by("id"))

    for ro in RequisitionOrder.objects.filter(task=task).order_by("-date_raised"):
        snap["ros"].append(
            {
                "ro_no": ro.ro_no,
                "status": ro.get_status_display(),
                "item_count": ro.items.count(),
            }
        )

    seen_rfq = set()
    for rfq in (
        RFQTransaction.objects.filter(bom_item__project_task=task)
        .select_related("supplier")
        .order_by("rfq_no")
    ):
        if rfq.rfq_no in seen_rfq:
            continue
        seen_rfq.add(rfq.rfq_no)
        snap["rfqs"].append(
            {
                "rfq_no": rfq.rfq_no,
                "supplier": rfq.supplier.description if rfq.supplier else "—",
                "selected": rfq.is_selected,
            }
        )

    lpos = list(
        LPOTransaction.objects.filter(project_task=task)
        .exclude(status=LPOTransaction.STATUS_CANCELLED)
        .select_related("supplier")
        .order_by("-date_issued")
    )
    any_received = False
    all_full = bool(lpos)
    for lpo in lpos:
        receipt = _lpo_receipt_status(lpo)
        if receipt in ("PARTIAL", "FULL"):
            any_received = True
        if receipt != "FULL":
            all_full = False
        snap["lpos"].append(
            {
                "lpo_no": lpo.lpo_no,
                "supplier": lpo.supplier.description if lpo.supplier else "—",
                "receipt": receipt,
                "total": f"{lpo.total_amount:,.2f}",
            }
        )

    if lpos:
        if all_full:
            snap["delivery_summary"] = "All LPO lines fully received (GRN complete)"
        elif any_received:
            snap["delivery_summary"] = "Partial delivery — GRN in progress"
        else:
            snap["delivery_summary"] = "Awaiting goods receipt (GRN)"

    if lane == "major":
        if lpos and all_full:
            snap["stage_label"] = "Delivered — all items received"
        elif lpos:
            snap["stage_label"] = "LPO issued — goods receipt"
        elif snap["rfqs"]:
            snap["stage_label"] = "RFQ / bid evaluation"
        elif snap["ros"]:
            snap["stage_label"] = "Requisition order (RO) raised"
        elif bom and bom.status != BOMHeader.STATUS_DRAFT:
            snap["stage_label"] = f"BOM {bom.bom_id} — {bom.get_status_display()}"
        elif bom and bom.items_locked:
            snap["stage_label"] = f"BOM {bom.bom_id} — locked, awaiting submit"
        elif bom:
            snap["stage_label"] = f"BOM {bom.bom_id} — draft"
        elif snap["budget_label"]:
            snap["stage_label"] = snap["budget_label"]
        else:
            snap["stage_label"] = "Major procurement in progress"
        snap["links"].extend(
            [
                {
                    "label": "RO Builder",
                    "url": reverse("ro_builder") + f"?task_id={task.project_id}",
                    "primary": True,
                },
                {
                    "label": "Bid Evaluation",
                    "url": reverse("bid_evaluation_terminal")
                    + f"?task_id={task.project_id}",
                    "primary": False,
                },
            ]
        )
    else:
        if bom and bom.items_locked and bom.status == BOMHeader.STATUS_DRAFT:
            snap["stage_label"] = "BOM locked — submit to finish your task here"
        elif bom and bom.items.exists():
            snap["stage_label"] = "BOM draft — add lines, then lock"
        else:
            snap["stage_label"] = "Ready to start BOM"

    return snap


def _bom_screen_lane(task):
    if not task:
        return "none"
    if _task_has_misc_po_path(task):
        return "misc"
    if _task_on_major_procurement_lane(task):
        return "major"
    return "bom"


def _get_task_bom(task):
    """One BOM row per task (dedupe legacy duplicates)."""
    if not task:
        return None
    rows = list(
        BOMHeader.objects.filter(task=task)
        .annotate(item_count=Count("items"))
        .order_by("-item_count", "-created_at", "-id")
    )
    if not rows:
        return None
    bom = rows[0]
    if not (bom.bom_id or "").strip():
        bom.save()
    for dup in rows[1:]:
        if dup.items.exists():
            dup.items.update(header=bom)
        dup.delete()
    return bom


def _task_meaningful_bom_header(task):
    """BOM that counts for display — ignore empty phantom headers from old auto-create."""
    bom = _get_task_bom(task)
    if not bom:
        return None
    if bom.status != BOMHeader.STATUS_DRAFT:
        return bom
    if bom.items_locked or bom.items.exists():
        return bom
    return None


def _ops_task_panel_context(task):
    """Lane + procurement status for ops dashboard (no misleading BOM numbers)."""
    if not task:
        return {
            "lane_label": "No task selected",
            "status_hint": "",
            "bom_display": "—",
            "bom_applicable": False,
        }
    hint = _bom_task_sidebar_hint(task)
    if _task_has_misc_po_path(task):
        return {
            "lane_label": "Ad-hoc · Lane X (Misc PO)",
            "status_hint": hint,
            "bom_display": "Not applicable",
            "bom_applicable": False,
        }
    bom = _task_meaningful_bom_header(task)
    if bom:
        return {
            "lane_label": "Major · Lane Y (BOM path)",
            "status_hint": hint,
            "bom_display": bom.bom_id,
            "bom_applicable": True,
        }
    return {
        "lane_label": "Uncommitted — Major BOM or Misc PO",
        "status_hint": hint,
        "bom_display": "No BOM started",
        "bom_applicable": False,
    }


def _bom_page_heading(task, screen_lane, *, can_start_bom=False, has_existing_bom=False, print_bom_pdf_url=""):
    """Top-of-page heading copy for BOM Builder (create / exists / misc)."""
    if not task:
        return {
            "mode": "select",
            "message": "Select a task from the list to review the BOM path.",
            "show_view_pdf": False,
            "view_pdf_url": "",
        }
    tid = task.project_id
    desc = task.description or ""
    if screen_lane == "misc":
        return {
            "mode": "misc",
            "message": (
                f"This Task: {tid} · {desc} is already using an alternative process "
                f"that does NOT require BOM."
            ),
            "show_view_pdf": False,
            "view_pdf_url": "",
        }
    if screen_lane == "major" or (has_existing_bom and not can_start_bom):
        return {
            "mode": "exists",
            "message": (
                f"You cannot Create a BOM for {tid} · {desc} — a project BOM already exists. "
                f"You can view that BOM using the button below."
            ),
            "show_view_pdf": bool(print_bom_pdf_url),
            "view_pdf_url": print_bom_pdf_url,
        }
    return {
        "mode": "create",
        "message": (
            f"Creating BOM for {tid} · {desc}. Please confirm if this Task requires "
            f"a BOM Process as specified herein below."
        ),
        "show_view_pdf": False,
        "view_pdf_url": "",
    }


@login_required
def bom_builder(request):
    """BOM path for Snr Site Engineer — all tasks visible; create BOM only when allowed."""
    from django.db import IntegrityError, transaction
    from django.urls import reverse

    active_task = _task_from_request(
        request, ProjectTask.objects.all(), include_post=(request.method == "POST")
    )
    redirect_url = (
        reverse("bom_builder") + f"?task_id={active_task.project_id}"
        if active_task
        else reverse("bom_builder")
    )

    def _render(**extra):
        ctx = {
            "task_rows": _bom_builder_task_rows(),
            "active_task": active_task,
            "task_status": None,
            "can_start_bom": False,
            "bom_items": [],
            "bom_no": "",
            "bom_mode": "none",
            "bom_locked": False,
            "bom_submitted": False,
            "screen_lane": "none",
            "engineer_journey_visible": False,
            "can_print_bom": False,
            "print_bom_url": "",
            "print_bom_pdf_url": "",
            "bom_heading": None,
        }
        ctx.update(extra)
        return render(request, "bom_builder.html", ctx)

    if not active_task:
        return _render(
            engineer_journey_visible=True,
            setup_message="Select any task — status shown in the list. Start BOM only on new major-lane tasks.",
            bom_heading=_bom_page_heading(None, "none"),
        )

    screen_lane = _bom_screen_lane(active_task)
    task_status = _bom_task_status_snapshot(active_task)

    if screen_lane == "misc":
        return _render(
            screen_lane="misc",
            task_status=task_status,
            bom_heading=_bom_page_heading(active_task, screen_lane),
        )
    if screen_lane == "major":
        bom_info = task_status.get("bom") or {}
        meaningful_bom = _task_meaningful_bom_header(active_task)
        print_bom_pdf_url = ""
        if meaningful_bom:
            print_bom_pdf_url = (
                reverse("print_bom_pdf") + f"?task_id={active_task.project_id}"
            )
        return _render(
            screen_lane="major",
            task_status=task_status,
            bom_items=task_status.get("bom_items") or [],
            bom_no=bom_info.get("bom_id", ""),
            bom_mode="detail" if bom_info else "none",
            bom_submitted=bom_info.get("status_code") != BOMHeader.STATUS_DRAFT
            if bom_info
            else False,
            can_print_bom=bool(meaningful_bom),
            print_bom_pdf_url=print_bom_pdf_url,
            bom_heading=_bom_page_heading(
                active_task,
                screen_lane,
                has_existing_bom=bool(meaningful_bom or bom_info),
                print_bom_pdf_url=print_bom_pdf_url,
            ),
        )

    bom_header = _get_task_bom(active_task)
    can_start_bom = task_status["can_create_bom"]

    if request.method == "POST":
        try:
            with transaction.atomic():
                if "new_bom" in request.POST:
                    if not can_start_bom:
                        raise ValueError(
                            "Cannot start a BOM on this task — see current status above."
                        )
                    if bom_header and bom_header.items.exists():
                        messages.info(
                            request,
                            f"Continuing BOM {bom_header.bom_id} — add lines below.",
                        )
                    elif bom_header and bom_header.items_locked:
                        raise ValueError(f"BOM {bom_header.bom_id} is locked.")
                    else:
                        if not bom_header:
                            try:
                                bom_header = BOMHeader.objects.create(
                                    task=active_task,
                                    status=BOMHeader.STATUS_DRAFT,
                                )
                            except IntegrityError:
                                bom_header = _get_task_bom(active_task)
                        if bom_header and not (bom_header.bom_id or "").strip():
                            bom_header.save()
                        messages.success(
                            request,
                            f"BOM {bom_header.bom_id} started — list item, UOM and quantity.",
                        )

                elif bom_header and "add_item" in request.POST:
                    if bom_header.items_locked:
                        raise ValueError("BOM lines are locked.")
                    if bom_header.status != BOMHeader.STATUS_DRAFT:
                        raise ValueError("This BOM has been submitted.")
                    BOMItem.objects.create(
                        header=bom_header,
                        pillar_id=int(request.POST.get("pillar_id") or 2),
                        description=(request.POST.get("description") or "").strip(),
                        qty=request.POST.get("qty", 0) or 0,
                        uom=(request.POST.get("uom") or "EA")[:50],
                    )
                    messages.success(request, "Line added to BOM.")

                elif bom_header and "delete_item" in request.POST:
                    if bom_header.items_locked:
                        raise ValueError("BOM lines are locked.")
                    BOMItem.objects.filter(
                        pk=request.POST.get("item_id"), header=bom_header
                    ).delete()
                    messages.success(request, "Line removed.")

                elif bom_header and "lock_bom" in request.POST:
                    if not bom_header.items.exists():
                        raise ValueError("Add at least one line before locking.")
                    if bom_header.items_locked:
                        raise ValueError("BOM is already locked.")
                    bom_header.items_locked = True
                    bom_header.save(update_fields=["items_locked"])
                    messages.success(
                        request,
                        "BOM item count locked. Submit when ready — your task on this screen is then complete.",
                    )

                elif bom_header and "submit_bom" in request.POST:
                    if not bom_header.items_locked:
                        raise ValueError("Lock the BOM item list before submitting.")
                    bom_header.status = BOMHeader.STATUS_SENT_TO_GM
                    bom_header.save(update_fields=["status"])
                    messages.success(
                        request,
                        f"BOM {bom_header.bom_id} submitted — print for signature and raise RO next.",
                    )
        except ValueError as exc:
            messages.error(request, str(exc))
        return redirect(redirect_url)

    bom_header = _get_task_bom(active_task)
    if not bom_header:
        bom_mode = "empty"
        bom_locked = bom_submitted = False
    elif bom_header.status != BOMHeader.STATUS_DRAFT:
        bom_mode = "detail"
        bom_locked = bom_submitted = True
    elif bom_header.items_locked:
        bom_mode = "locked"
        bom_locked = True
        bom_submitted = False
    elif bom_header.items.exists():
        bom_mode = "draft"
        bom_locked = bom_submitted = False
    else:
        bom_mode = "empty"
        bom_locked = bom_submitted = False

    engineer_journey_visible = bom_mode in ("empty", "draft", "locked") and not bom_submitted
    can_print_bom = bool(
        bom_header and bom_header.items.exists() and (bom_locked or bom_submitted)
    )
    print_bom_url = print_bom_pdf_url = ""
    if can_print_bom and bom_header:
        print_bom_url = reverse("print_bom") + f"?task_id={active_task.project_id}&print=1"
        print_bom_pdf_url = reverse("print_bom_pdf") + f"?task_id={active_task.project_id}"

    return _render(
        screen_lane="bom",
        task_status=task_status,
        can_start_bom=can_start_bom,
        bom_header=bom_header,
        bom_items=bom_header.items.all().order_by("id") if bom_header else [],
        bom_no=bom_header.bom_id if bom_header else "",
        bom_mode=bom_mode,
        bom_locked=bom_locked,
        bom_submitted=bom_submitted,
        engineer_journey_visible=engineer_journey_visible,
        can_print_bom=can_print_bom,
        print_bom_url=print_bom_url,
        print_bom_pdf_url=print_bom_pdf_url,
        bom_heading=_bom_page_heading(
            active_task,
            screen_lane,
            can_start_bom=can_start_bom,
            has_existing_bom=bool(_task_meaningful_bom_header(active_task))
            and not can_start_bom,
            print_bom_pdf_url=print_bom_pdf_url if can_print_bom else "",
        ),
    )


def _bom_print_context(request, *, task=None, bom=None, ro=None):
    """Shared context for BOM print / PDF views."""
    if ro and not task:
        task = ro.task
    if not task:
        task_id = request.GET.get("task_id")
        task = get_object_or_404(ProjectTask, project_id=task_id)
    if not bom:
        bom = _get_task_bom(task)
        if not bom and ro:
            bom = BOMHeader.objects.filter(ro=ro).first()
    if not bom:
        return None
    if not (bom.bom_id or "").strip():
        return None
    if not bom.items.exists():
        return None
    back_url = request.GET.get("return") or (
        reverse("bom_builder") + f"?task_id={task.project_id}"
    )
    context = {
        "bom_no": bom.bom_id,
        "bom_items": bom.items.all().order_by("id"),
        "active_task": task,
        "bom_status": bom.get_status_display(),
        "bom_date": bom.created_at,
        "auto_print": request.GET.get("print") == "1",
        "back_url": back_url,
    }
    context.update(branding_template_context(request))
    return context


@login_required
def print_bom_view(request):
    """Letterhead BOM print from BOM Builder (screen preview + browser print)."""
    context = _bom_print_context(request)
    if not context:
        messages.error(
            request,
            "Cannot print: this task has no BOM with line items yet.",
        )
        task_id = request.GET.get("task_id", "")
        return redirect(reverse("bom_builder") + (f"?task_id={task_id}" if task_id else ""))
    context["auto_print"] = request.GET.get("print") == "1"
    return render(request, "bom_print.html", context)


@login_required
def print_bom_pdf_view(request):
    """Same bom_print.html layout — opens browser print (Save as PDF), not xhtml2pdf."""
    context = _bom_print_context(request)
    if not context:
        messages.error(
            request,
            "Cannot print: this task has no BOM with line items yet.",
        )
        task_id = request.GET.get("task_id", "")
        return redirect(reverse("bom_builder") + (f"?task_id={task_id}" if task_id else ""))
    context["auto_print"] = True
    return render(request, "bom_print.html", context)

# =======================================================================
# ⚖️ THE ULTIMATE SINGLE UNIFIED RFQ & TENDER MONITOR ENGINE
# =======================================================================
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from .models import ProjectTask, RequisitionOrder, SupplierAccount, RFQTransaction

@login_required
def rfq_manager(request):
    """
    Refactored RFQ Dashboard Terminal.
    Coordinates active task prescriptions with tail-end Vault selections.
    """
    tasks = ProjectTask.objects.all()
    suppliers = SupplierAccount.objects.all()
    total_qualified_suppliers = suppliers.count()
    active_task = _task_from_request(request, tasks)

    build_items = []
    stats = {"sent_count": 0, "waiting_count": 0}

    if active_task:
        ro = RequisitionOrder.objects.filter(task=active_task).first()
        if ro:
            build_items = ro.items.all().order_by("id")
            item_ids = build_items.values_list("id", flat=True)
            sent_transactions = RFQTransaction.objects.filter(bom_item_id__in=item_ids)
            stats["sent_count"] = sent_transactions.values("supplier_id").distinct().count()
            stats["waiting_count"] = (
                sent_transactions.filter(is_selected=False)
                .values("supplier_id")
                .distinct()
                .count()
            )

    return render(request, "rfq_manager.html", {
        "tasks": tasks,
        "active_task": active_task,
        "build": build_items,
        "suppliers": suppliers,
        "total_qualified_suppliers": total_qualified_suppliers,
        'stats': stats
    })
# ======================================================================================================================
from decimal import Decimal
import json

from django.contrib import messages
from django.db import transaction
from django.shortcuts import render, redirect
from django.urls import reverse

from .models import (
    ProjectTask,
    BOMTransaction,
    RFQTransaction,
    ProjectBudget,
    BudgetTransaction,
    SupplierAccount,
)


def bid_evaluation_view(request):

    # =========================================================
    # LOAD TASK
    # =========================================================
    task_id = request.GET.get("task_id")

    active_task = (
        ProjectTask.objects.filter(project_id=task_id).first()
        if task_id
        else ProjectTask.objects.first()
    )

    if not active_task:
        messages.error(request, "No active project task found.")
        return redirect("dashboard")

    # =========================================================
    # LOAD BOM ITEMS FOR THIS TASK ONLY
    # =========================================================
    bom_items = BOMTransaction.objects.filter(
        project_task=active_task
    ).select_related("product")

    # =========================================================
    # LOAD SUPPLIERS
    # =========================================================
    suppliers = SupplierAccount.objects.all()[:2]

    # =========================================================
    # POST PROCESSING
    # =========================================================
    if request.method == "POST":

        try:

            with transaction.atomic():

                # =================================================
                # FINANCIAL TOTALS
                # =================================================
                material_total = Decimal(
                    request.POST.get("material_total", "0")
                )

                misc_reserve = Decimal(
                    request.POST.get("misc_input", "0")
                )

                labour_mode = request.POST.get("labour_mode")

                labour_input = Decimal(
                    request.POST.get("labour_input", "0")
                )

                # =================================================
                # LABOUR CALCULATION
                # =================================================
                if labour_mode == "percent":
                    labour_burden = (
                        material_total * labour_input
                    ) / Decimal("100")
                else:
                    labour_burden = labour_input

                total_budget = (
                    material_total
                    + labour_burden
                    + misc_reserve
                )

                # =================================================
                # CREATE OR UPDATE BUDGET
                # =================================================
                rfq_ok, rfq_reason = _rfq_channel_allowed(active_task)
                if not rfq_ok:
                    raise ValueError(rfq_reason)

                budget = _save_task_budget(
                    active_task,
                    ProjectBudget.BUDGET_RFQ_LPO,
                    material_total,
                    labour_burden,
                    misc_reserve,
                    total_budget,
                    label=f"BUDGET-{active_task.project_id}",
                )
                budget.version += 1
                budget.save(update_fields=["version"])

                # =================================================
                # CLEAR OLD TRANSACTIONS
                # =================================================
                budget.transactions.all().delete()

                # =================================================
                # CREATE MATERIAL TRANSACTION
                # =================================================
                BudgetTransaction.objects.create(
                    budget=budget,
                    category="MATERIAL",
                    amount=material_total,
                    description=f"Material Cost Allocation - {active_task.project_id}",
                )

                # =================================================
                # CREATE LABOUR TRANSACTION
                # =================================================
                if labour_burden > 0:
                    BudgetTransaction.objects.create(
                        budget=budget,
                        category="LABOUR",
                        amount=labour_burden,
                        description=f"Labour Burden Allocation - {active_task.project_id}",
                    )

                # =================================================
                # CREATE MISC TRANSACTION
                # =================================================
                if misc_reserve > 0:
                    BudgetTransaction.objects.create(
                        budget=budget,
                        category="MISC",
                        amount=misc_reserve,
                        description=f"Misc Reserve Allocation - {active_task.project_id}",
                    )

                # =================================================
                # SAVE RFQ UNIT PRICES
                # =================================================
                for item in bom_items:

                    winner_price = Decimal(
                        request.POST.get(f"winner_{item.id}", "0")
                    )

                    runner_price = Decimal(
                        request.POST.get(f"runner_{item.id}", "0")
                    )

                    RFQTransaction.objects.update_or_create(
                        bom_item=item,
                        defaults={
                            "unit_cost_quoted": winner_price,
                        },
                    )

                # =================================================
                # SUCCESS
                # =================================================
                messages.success(
                    request,
                    f"Budget successfully committed for Task {active_task.project_id}"
                )

                return redirect(
                    reverse("bid_evaluation")
                    + f"?task_id={active_task.project_id}"
                )

        except Exception as e:

            messages.error(
                request,
                f"System Error: {str(e)}"
            )

            return redirect(request.path)

    # =========================================================
    # GET REQUEST
    # =========================================================
    context = {
        "active_task": active_task,
        "tasks": ProjectTask.objects.all(),
        "bom_items": bom_items,
        "suppliers": suppliers,
    }

    return render(
        request,
        "bid_evaluation.html",
        context
    )
# =======================================================================
# 💰 PROCUREMENT, LPO & FINANCIAL SETTLEMENT TRANSACTIONS
# =======================================================================
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from decimal import Decimal, InvalidOperation
from .models import (
    ProjectTask, RequisitionOrder, RequisitionOrderItem, 
    SupplierAccount, RFQTransaction, LPOTransaction, 
    ProjectBuilding, ProjectBuildCategory
)
# ========================================================================
from decimal import Decimal
from django.utils import timezone
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from .models import (
    ProjectTask,
    SupplierAccount,
    RFQTransaction,
    LPOTransaction,
    BOMTransaction,
)

def _build_lpo_print_context(task_id, supplier_id):
    active_task = ProjectTask.objects.filter(project_id=task_id).first()
    if not active_task:
        return None

    winning_supplier = SupplierAccount.objects.filter(supplier_id=supplier_id).first()
    template_items = []
    materials_total = Decimal("0.00")
    lpo_no = f"LPO-{active_task.project_id}-{timezone.now().strftime('%m%d%H%M')}"
    saved_lpo = None

    winning_quotes = RFQTransaction.objects.filter(
        bom_item__project_task=active_task, is_selected=True
    ).select_related("supplier", "bom_item", "bom_item__product")

    if winning_quotes.exists():
        for idx, quote in enumerate(winning_quotes, start=1):
            bom = quote.bom_item
            qty = bom.quantity_required or Decimal("0.00")
            unit_price = quote.unit_cost_quoted or Decimal("0.00")
            line_total = qty * unit_price
            materials_total += line_total
            template_items.append({
                "id": idx,
                "desc": bom.product.description if bom.product else "Material Item",
                "qty": qty,
                "uom": getattr(bom.product, "unit_of_measure", "PCS"),
                "price": unit_price,
                "total": line_total,
            })
    else:
        lpo_qs = LPOTransaction.objects.filter(project_task=active_task).prefetch_related("items")
        if winning_supplier:
            lpo_qs = lpo_qs.filter(supplier=winning_supplier)
        saved_lpo = lpo_qs.order_by("-date_issued").first()
        if saved_lpo:
            lpo_no = saved_lpo.lpo_no
            materials_total = saved_lpo.total_amount or Decimal("0")
            if not winning_supplier:
                winning_supplier = saved_lpo.supplier
            for idx, line in enumerate(saved_lpo.items.all(), start=1):
                template_items.append({
                    "id": idx,
                    "desc": line.description,
                    "qty": line.qty,
                    "uom": line.uom,
                    "price": line.unit_price,
                    "total": line.total_price,
                })

    return {
        "task": active_task,
        "items": template_items,
        "supplier_account": winning_supplier,
        "winning_supplier": winning_supplier.description if winning_supplier else "Approved Vendor",
        "materials_total": materials_total,
        "order_total": materials_total,
        "lpo_no": lpo_no,
        "date": timezone.now().strftime("%B %d, %Y"),
        "saved_lpo": saved_lpo,
    }


@login_required
def procurement_lpo(request):
    task_id = request.GET.get("task_id")
    context = _build_lpo_print_context(task_id, request.GET.get("supplier_id"))
    if not context:
        messages.error(request, "No task selected for LPO.")
        return redirect("dashboard")

    context["pdf_saved"] = False
    try:
        from pathlib import Path
        from django.conf import settings
        import re

        safe = re.sub(r"[^\w\-]", "_", str(context["lpo_no"]))[:80]
        media = getattr(settings, "MEDIA_ROOT", None) or Path(settings.BASE_DIR) / "media"
        context["pdf_saved"] = (Path(media) / "lpo_pdfs" / f"{safe}.pdf").exists()
    except Exception:
        pass

    return render(request, "procurement_lpo_view.html", context)


@login_required
def lpo_export_pdf(request):
    from django.http import HttpResponse
    from accounts.lpo_pdf import build_pdf_bytes, save_lpo_pdf, lpo_pdf_filepath

    task_id = request.GET.get("task_id")
    supplier_id = request.GET.get("supplier_id")
    context = _build_lpo_print_context(task_id, supplier_id)
    if not context:
        messages.error(request, "No task selected for LPO.")
        return redirect("dashboard")
    context.update(branding_template_context(request))

    try:
        if request.GET.get("save") == "1":
            save_lpo_pdf(context["lpo_no"], context)
            messages.success(request, f"PDF saved: {context['lpo_no']}.pdf")
        pdf_bytes = build_pdf_bytes(context)
    except ImportError:
        messages.error(request, "Install PDF support: pip install xhtml2pdf")
        return redirect(
            f"/lpo-dispatch/?task_id={task_id}&supplier_id={supplier_id or ''}"
        )
    except Exception as e:
        messages.error(request, f"PDF failed: {e}")
        return redirect(
            f"/lpo-dispatch/?task_id={task_id}&supplier_id={supplier_id or ''}"
        )

    filename = f"{context['lpo_no']}.pdf"
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
# ======================================================================================================LPO END

from django.shortcuts import render
from .models import LPOTransaction

@login_required
def lpo_list_view(request):
    lpos = LPOTransaction.objects.select_related(
        "project_task",
        "supplier",
    ).order_by("-date_issued")

    return render(request, 'lpo_list.html', {
        'lpos': lpos
    })

# ========================================================================================================



import json
from datetime import date
#from django.shortcuts import render, get_object_or_worry # Use your standard imports
#from .models import Supplier # Adjust this to your actual app model location


def lpo_settlement_view(request):
    # 1. Safely pull your project details
    project_id = request.GET.get('project_id', '1')
    description = request.GET.get('description', 'Infrastructure Project')
    
    # 2. Extract the manually selected supplier IDs (e.g., '2,1') safely using pk__in
    supplier_ids_raw = request.GET.get('supplier_id', '')
    supplier_account = None
    winning_supplier_name = ""
    
    if supplier_ids_raw:
        # Split string and strip whitespace: ['2', '1']
        supplier_id_list = [sid.strip() for sid in supplier_ids_raw.split(',') if sid.strip()]
        
        # Use primary key (pk__in) to sidestep the implicit 'id' lookup FieldError
        suppliers = Supplier.objects.filter(pk__in=supplier_id_list)
        
        if suppliers.exists():
            # Get the primary target for the LPO issue profile
            supplier_account = suppliers.first()
            winning_supplier_name = supplier_account.description

    # 3. Parse and re-map the JSON items data to match template variables
    items_raw = request.GET.get('items_json', '[]')
    template_items = []
    materials_total = 0.0

    try:
        parsed_items = json.loads(items_raw)
        for idx, item in enumerate(parsed_items, start=1):
            # Extract raw values from URL mapping format
            qty = float(item.get('qty', 0))
            # Match 'unit_price' key from payload, fallback to 'price'
            unit_price = float(item.get('unit_price', item.get('price', 0)))
            line_total = float(item.get('line_total', qty * unit_price))
            
            # Recompute total safely to ensure accounting alignment
            materials_total += line_total
            
            # Map parameters explicitly to match your template loops
            template_items.append({
                'id': item.get('id', str(idx)),
                'desc': item.get('desc', 'Material Line Item'),
                'qty': qty,
                'uom': item.get('uom', 'PCS'),
                'price': unit_price,   # Maps directly to {{ item.price }}
                'total': line_total,   # Maps directly to {{ item.total }}
            })
    except (json.JSONDecodeError, TypeError, ValueError):
        template_items = []
        # Fallback total calculation if needed
        materials_total = float(request.GET.get('material_cost', 0.0))

    # 4. Construct a mockup task structure matching your layout references
    task_mock = {
        'project_id': project_id,
        'description': description,
    }

    # 5. Pack the context dictionary precisely for the HTML template fields
    context = {
        'lpo_no': f"LPO-20260522-DEMO", # Matches {{ lpo_no }}
        'date': date.today().strftime("%B %d, %Y"), # Matches {{ date }}
        'supplier_account': supplier_account, # Matches {{ supplier_account.* }}
        'winning_supplier': winning_supplier_name, # Fallback name
        'task': task_mock, # Matches {{ task.project_id }} and {{ task.description }}
        'items': template_items, # MATCHES YOUR TEMPLATE LOOP: {% for item in items %}
        'materials_total': materials_total, # Matches {{ materials_total }}
    }

    return render(request, 'procurement/lpo_print_template.html', context)
# =======================================================================
# 🖨️ CLEAN UNIFIED DOCUMENTATION PRINT VISUALIZERS
# =======================================================================

# ==========================================
# 🖨️ THE RESTORED DISBURSEMENT PRINT VIEW 
# ==========================================
@login_required
def print_memo_view(request, task_id):
    from types import SimpleNamespace

    active_task = get_object_or_404(ProjectTask, project_id=task_id)
    build_items = BOMItem.objects.filter(header__task=active_task)

    supplier_account = None
    supplier_id = request.GET.get("supplier_id")
    if supplier_id:
        supplier_account = SupplierAccount.objects.filter(supplier_id=supplier_id).first()

    winner_label = request.GET.get("winner", "Approved Vendor")
    if supplier_account:
        winner_label = supplier_account.description

    materials_total = Decimal(request.GET.get("mat", 0) or 0)
    labour_total = Decimal(request.GET.get("labour", 0) or 0)
    misc_total = Decimal(request.GET.get("misc", 0) or 0)
    grand_total = materials_total + labour_total + misc_total

    winning_supplier = supplier_account or SimpleNamespace(
        description=winner_label,
        supplier_id=supplier_id or "",
    )

    return render(
        request,
        "procurement_memo.html",
        {
            "active_task": active_task,
            "task": active_task,
            "build": build_items,
            "winning_supplier": winning_supplier,
            "supplier_account": winning_supplier,
            "materials_total": materials_total,
            "labour_total": labour_total,
            "misc_total": misc_total,
            "mat_total": materials_total,
            "lab_total": labour_total,
            "grand_total": grand_total,
        },
    )
@login_required
def print_ro_view(request, ro_id):
    ro = get_object_or_404(RequisitionOrder, id=ro_id)
    return render(request, "ro_print_template.html", {"ro": ro, "items": ro.items.all()})

@login_required
def print_lpo_view(request, lpo_id):
    """Print saved LPO with Pioneer letterhead (supplier + line items)."""
    lpo = get_object_or_404(
        LPOTransaction.objects.select_related("supplier", "project_task").prefetch_related(
            "items"
        ),
        id=lpo_id,
    )
    template_items = []
    materials_total = Decimal("0.00")
    for idx, line in enumerate(lpo.items.all(), start=1):
        line_total = line.total_price or Decimal("0.00")
        materials_total += line_total
        template_items.append({
            "id": idx,
            "desc": line.description,
            "qty": line.qty,
            "uom": line.uom,
            "price": line.unit_price,
            "total": line_total,
        })
    if not materials_total and lpo.total_amount:
        materials_total = lpo.total_amount

    supplier = lpo.supplier
    context = {
        "task": lpo.project_task,
        "items": template_items,
        "supplier_account": supplier,
        "winning_supplier": supplier.description if supplier else "Approved Vendor",
        "materials_total": materials_total,
        "order_total": materials_total,
        "lpo_no": lpo.lpo_no,
        "date": timezone.localtime(lpo.date_issued).strftime("%B %d, %Y"),
        "saved_lpo": lpo,
        "lpo": lpo,
        "pdf_saved": False,
    }
    return render(request, "procurement_lpo_view.html", context)
# =====================================================================
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from .models import ProjectTask, RequisitionOrder, SupplierAccount

@login_required
def print_rfq_letter(request):
    """
    Engine to process batch supplier arrays and map them cleanly 
    to the rfq_print_letter.html loop structure.
    """
    # 1. Pull incoming query parameters from the dashboard request
    task_id = request.GET.get('task_id')
    supplier_ids_raw = request.GET.get('supplier_ids', '') # Reads the comma-separated array string
    
    # 2. Get the target Project Task record safely
    active_task = get_object_or_404(ProjectTask, project_id=task_id)
    
    # 3. Pull the active Requisition Order (RO) generated by the Site Manager
    ro = RequisitionOrder.objects.filter(task=active_task).first()
    
    if ro:
        # Pull the exact RequisitionOrderItem lines synced from the BOM plan
        items_payload = ro.items.all().order_by('id')
        display_ro_no = ro.ro_no
    else:
        display_ro_no = f"RFQ-{active_task.project_id}"
        items_payload = []

    # 4. Parse the comma-separated supplier string back into a clean Python list
    supplier_id_list = [sid.strip() for sid in supplier_ids_raw.split(',') if sid.strip()]
    
    # 5. Fetch all targeted suppliers matching that array selection matrix
    selected_suppliers = SupplierAccount.objects.filter(supplier_id__in=supplier_id_list)

    # 6. Build the structural packets array expected by the template's master loop
    supplier_packets = []
    for supplier in selected_suppliers:
        supplier_packets.append({
            'supplier': supplier,
            'ro_no': display_ro_no,
            'items': items_payload
        })

    # 7. Deliver to the template layer
    from django.urls import reverse

    return_url = reverse("rfq_manager") + f"?task_id={active_task.project_id}"
    return render(request, 'rfq_print_letter.html', {
        'task': active_task,
        'today': timezone.now(),
        'supplier_packets': supplier_packets,
        'return_url': return_url,
    })
# ======================================================================
@login_required
def print_bom_from_ro(request, ro_id):
    ro = get_object_or_404(RequisitionOrder, id=ro_id)
    bom = BOMHeader.objects.filter(ro=ro).first()
    if not bom:
        bom = _get_task_bom(ro.task)

    if not bom:
        bom, _ = BOMHeader.objects.get_or_create(
            task=ro.task,
            defaults={"ro": ro, "status": BOMHeader.STATUS_GENERATED},
        )
        if bom.ro_id != ro.id:
            bom.ro = ro
            bom.status = BOMHeader.STATUS_GENERATED
            bom.save(update_fields=["ro", "status"])
        for item in ro.items.all():
            BOMItem.objects.create(
                header=bom,
                pillar_id=2,
                description=item.product.description
                if item.product
                else item.tech_spec_summary,
                qty=item.quantity,
                uom=item.uom,
                unit_price=0,
            )
    elif not bom.items.exists():
        for item in ro.items.all():
            BOMItem.objects.create(
                header=bom,
                pillar_id=2,
                description=item.product.description
                if item.product
                else item.tech_spec_summary,
                qty=item.quantity,
                uom=item.uom,
                unit_price=0,
            )

    context = _bom_print_context(request, task=ro.task, bom=bom, ro=ro)
    if not context:
        messages.error(request, "Could not build BOM print context.")
        return redirect("bom_builder")
    return render(request, "bom_print.html", context)
    
# ==========================================================
from django.db import transaction
from decimal import Decimal

def perform_procurement_sync(
    task,
    item,
    winner,
    runner,
    w_price,
    r_price,
    lpo_no
):

    with transaction.atomic():

        # =====================================================
        # RFQ WINNER
        # =====================================================
        quote_record, _ = RFQTransaction.objects.update_or_create(
            bom_item=item,
            supplier=winner,
            defaults={
                "unit_cost_quoted": Decimal(w_price),
                "is_selected": True
            }
        )

        # =====================================================
        # RFQ RUNNER
        # =====================================================
        RFQTransaction.objects.update_or_create(
            bom_item=item,
            supplier=runner,
            defaults={
                "unit_cost_quoted": Decimal(r_price),
                "is_selected": False
            }
        )

        # =====================================================
        # SAFE LPO CREATION
        # =====================================================
        lpo = LPOTransaction.objects.create(

            lpo_no=lpo_no,

            supplier=winner,

            project_task=task,

            # SAFE FALLBACKS
            building=ProjectBuilding.objects.first(),

            build_category=item.build_category,

            variance_explanation=(
                f"WIN:{winner.description} | "
                f"MAT:{w_price}"
            ),

            stars=5
        )

        # =====================================================
        # SAFE BUDGET CREATION
        # =====================================================
        ProjectBudget.objects.get_or_create(

            task=task,

            defaults={

                "budget_label":
                    f"{task.project_id} PROCUREMENT BASELINE",

                "material_total_cost":
                    Decimal(w_price),

                "labour_burden":
                    Decimal("0.00"),

                "misc_reserve":
                    Decimal("0.00"),

                "total_authorized_budget":
                    Decimal(w_price)
            }
        )

        return lpo
# ===================================================================================

def resolve_source_items(active_task):
    # Logic to fetch items related to the task
    # Replace 'ItemModel' with your actual Model name
    final_items = active_task.items.all() 
    source_type = "Standard"
    return final_items, source_type

from django.http import HttpResponse


from django.shortcuts import render, redirect, get_object_or_404
from django.db import transaction
from django.contrib import messages
from django.contrib.auth.decorators import login_required
import json
from accounts.forms import BudgetForm, LPOTransactionForm, LPOItemFormSet # <--- Updated

from django.shortcuts import render, redirect



from django.shortcuts import get_object_or_404, redirect, render
from django.db import transaction
from django.contrib import messages
import json

def _money(post, key, default="0"):
    val = post.get(key, default)
    if not val or str(val).strip() == "":
        val = default
    return Decimal(str(val))


def _build_task_budget_status(task):
    """Materials line: budget vs LPO ordered cost vs variance (Material − LPO)."""
    empty = {
        "authorized": "0.00",
        "material": "0.00",
        "labour": "0.00",
        "misc": "0.00",
        "lpo_material": "0.00",
        "material_variance": "0.00",
        "variance_over": False,
        "committed": "0.00",
        "used": "0.00",
        "reserved": "0.00",
        "remaining": "0.00",
        "has_budget": False,
        "lpo_count": 0,
        "version": 0,
        "label": "",
    }
    if not task:
        return empty

    budget = ProjectBudget.objects.filter(task=task).first()
    authorized = budget.total_authorized_budget if budget else Decimal("0")
    material = budget.material_total_cost if budget else Decimal("0")
    labour = budget.labour_burden if budget else Decimal("0")
    misc = budget.misc_reserve if budget else Decimal("0")

    lpo_material = (
        LPOItem.objects.filter(lpo__project_task=task)
        .exclude(lpo__status=LPOTransaction.STATUS_CANCELLED)
        .aggregate(t=Sum("total_price"))["t"]
        or Decimal("0")
    )
    if lpo_material == 0:
        lpo_material = (
            LPOTransaction.objects.filter(project_task=task)
            .exclude(status=LPOTransaction.STATUS_CANCELLED)
            .aggregate(t=Sum("total_amount"))["t"]
            or Decimal("0")
        )

    material_variance = material - lpo_material
    committed = lpo_material

    used = Decimal("0")
    if budget:
        used = budget.transactions.filter(category="MATERIAL").aggregate(t=Sum("amount"))["t"] or Decimal("0")
        if used == 0:
            used = budget.transactions.aggregate(t=Sum("amount"))["t"] or Decimal("0")
    if used == 0:
        used = (
            PaymentOrder.objects.filter(
                grn__lpo__project_task=task,
                is_confirmed_by_director=True,
            ).aggregate(t=Sum("grn__lpo__total_amount"))["t"]
            or Decimal("0")
        )

    reserved = max(committed - used, Decimal("0"))
    remaining = max(authorized - committed, Decimal("0"))

    def _fmt(val):
        return f"{val:.2f}"

    return {
        "authorized": _fmt(authorized),
        "material": _fmt(material),
        "labour": _fmt(labour),
        "misc": _fmt(misc),
        "lpo_material": _fmt(lpo_material),
        "material_variance": _fmt(material_variance),
        "variance_over": material_variance < 0,
        "committed": _fmt(committed),
        "used": _fmt(used),
        "reserved": _fmt(reserved),
        "remaining": _fmt(remaining),
        "has_budget": budget is not None,
        "lpo_count": LPOTransaction.objects.filter(project_task=task)
        .exclude(status=LPOTransaction.STATUS_CANCELLED)
        .count(),
        "version": budget.version if budget else 0,
        "label": budget.budget_label if budget else "",
    }


def _lpo_item_received_qty(lpo_item):
    return (
        GRNItem.objects.filter(lpo_item=lpo_item).aggregate(t=Sum("qty_received"))["t"]
        or Decimal("0")
    )


def _lpo_receipt_status(lpo):
    """Return NONE, PARTIAL, or FULL based on cumulative GRN lines."""
    lines = list(lpo.items.all())
    if not lines:
        return "NONE"
    any_received = False
    all_full = True
    for line in lines:
        received = _lpo_item_received_qty(line)
        if received > 0:
            any_received = True
        if received < line.qty:
            all_full = False
    if not any_received:
        return "NONE"
    return "FULL" if all_full else "PARTIAL"


def _serialize_task_lpos(task):
    from django.urls import reverse

    if not task:
        return []

    rows = []
    qs = (
        LPOTransaction.objects.filter(project_task=task)
        .select_related("supplier", "project_task")
        .prefetch_related("items", "grns")
        .order_by("-date_issued")
    )
    for lpo in qs:
        supplier = lpo.supplier
        sid = supplier.supplier_id if supplier else ""
        receipt_status = _lpo_receipt_status(lpo)
        rows.append({
            "id": lpo.id,
            "lpo_no": lpo.lpo_no,
            "status": lpo.status,
            "is_cancelled": lpo.status == LPOTransaction.STATUS_CANCELLED,
            "receipt_status": receipt_status,
            "grn_count": lpo.grns.count(),
            "supplier": supplier.description if supplier else "Unassigned",
            "supplier_id": sid,
            "supplier_phone": supplier.phone if supplier else "",
            "supplier_email": supplier.email if supplier else "",
            "supplier_address": supplier.contact_address if supplier else "",
            "supplier_bank": supplier.bank_account_number if supplier else "",
            "task_id": task.project_id,
            "task_description": task.description,
            "total": f"{lpo.total_amount:.2f}",
            "date": timezone.localtime(lpo.date_issued).strftime("%d %b %Y %H:%M"),
            "items": [
                {
                    "id": it.id,
                    "rfq_no": it.rfq_no or "",
                    "desc": it.description,
                    "qty": f"{it.qty}",
                    "qty_ordered": float(it.qty),
                    "qty_received": float(_lpo_item_received_qty(it)),
                    "qty_remaining": float(max(it.qty - _lpo_item_received_qty(it), Decimal("0"))),
                    "uom": it.uom,
                    "price": f"{it.unit_price:.2f}",
                    "total": f"{it.total_price:.2f}",
                }
                for it in lpo.items.all()
            ],
            "print_url": reverse("print_lpo_view", args=[lpo.id]),
            "dispatch_url": (
                reverse("procurement_lpo_view")
                + f"?task_id={task.project_id}&supplier_id={sid}"
            ),
        })
    return rows


def _serialize_lpo_goods_status(task):
    """LPO line items with index, cumulative delivery, outstanding, and GRN receipt history."""
    from django.urls import reverse

    if not task:
        return []

    lpos = list(
        LPOTransaction.objects.filter(project_task=task)
        .exclude(status=LPOTransaction.STATUS_CANCELLED)
        .select_related("supplier")
        .prefetch_related("items")
        .order_by("-date_issued")
    )
    if not lpos:
        return []

    lpo_ids = [lpo.id for lpo in lpos]
    deliveries_by_item = defaultdict(list)
    for grn_line in (
        GRNItem.objects.filter(lpo_item__lpo_id__in=lpo_ids)
        .select_related("grn", "lpo_item")
        .order_by("grn__receipt_date", "grn__date_received", "grn__id")
    ):
        grn = grn_line.grn
        if grn_line.qty_received <= 0:
            continue
        deliveries_by_item[grn_line.lpo_item_id].append({
            "grn_no": grn.grn_no,
            "grn_id": grn.id,
            "date": grn.receipt_date.strftime("%d %b %Y"),
            "qty": float(grn_line.qty_received),
            "print_url": reverse("print_grn_view", args=[grn.id]),
        })

    rows = []
    for lpo in lpos:
        items = []
        for idx, item in enumerate(lpo.items.all().order_by("id"), start=1):
            deliveries = deliveries_by_item.get(item.id, [])
            cumulative = sum(
                (Decimal(str(d["qty"])) for d in deliveries),
                Decimal("0"),
            )
            outstanding = max(item.qty - cumulative, Decimal("0"))
            if outstanding <= 0 and cumulative > 0:
                line_status = "FULL"
            elif cumulative > 0:
                line_status = "PARTIAL"
            else:
                line_status = "NONE"

            items.append({
                "index": idx,
                "item_id": item.id,
                "rfq_no": item.rfq_no or "",
                "description": item.description,
                "uom": item.uom,
                "qty_ordered": float(item.qty),
                "qty_delivered": float(cumulative),
                "qty_outstanding": float(outstanding),
                "unit_price": f"{item.unit_price:.2f}",
                "line_status": line_status,
                "deliveries": deliveries,
            })

        rows.append({
            "lpo_id": lpo.id,
            "lpo_no": lpo.lpo_no,
            "supplier": lpo.supplier.description if lpo.supplier else "Unassigned",
            "receipt_status": _lpo_receipt_status(lpo),
            "date_issued": timezone.localtime(lpo.date_issued).strftime("%d %b %Y"),
            "items": items,
        })
    return rows


def _grn_receipt_amount(grn):
    total = Decimal("0")
    for line in grn.lines.select_related("lpo_item").all():
        total += line.qty_received * line.lpo_item.unit_price
    return total


def _parse_month_period(from_month="", to_month=""):
    """Parse YYYY-MM strings into inclusive date range; default Jan 1 → today."""
    today = timezone.localdate()
    default_from = f"{today.year}-01"
    default_to = f"{today.year}-{today.month:02d}"

    def _month_bounds(value):
        if not value or len(value) != 7 or value[4] != "-":
            return None
        try:
            year, month = int(value[:4]), int(value[5:7])
            if month < 1 or month > 12:
                return None
            last_day = calendar.monthrange(year, month)[1]
            return date(year, month, 1), date(year, month, last_day)
        except (TypeError, ValueError):
            return None

    from_bounds = _month_bounds(from_month) or _month_bounds(default_from)
    to_bounds = _month_bounds(to_month) or _month_bounds(default_to)
    start_date, _ = from_bounds
    _, end_date = to_bounds
    if start_date > end_date:
        start_date, end_date = end_date, start_date
    period_from = f"{start_date.year}-{start_date.month:02d}"
    period_to = f"{end_date.year}-{end_date.month:02d}"
    return start_date, end_date, period_from, period_to


def _serialize_task_grns(task, start_date=None, end_date=None):
    from django.urls import reverse

    if not task:
        return []

    voucher_map = {
        pv.grn_id: pv
        for pv in PaymentOrder.objects.filter(grn__lpo__project_task=task).select_related(
            "source_bank"
        )
    }
    rows = []
    qs = (
        GRNTransaction.objects.filter(lpo__project_task=task)
        .select_related("lpo__supplier", "lpo")
        .prefetch_related("lines__lpo_item")
        .order_by("-receipt_date", "-date_received")
    )
    if start_date:
        qs = qs.filter(receipt_date__gte=start_date)
    if end_date:
        qs = qs.filter(receipt_date__lte=end_date)
    for grn in qs:
        lpo = grn.lpo
        supplier = lpo.supplier
        amount = _grn_receipt_amount(grn)
        pv = voucher_map.get(grn.id)
        has_invoice = bool((grn.invoice_ref or "").strip())
        rows.append({
            "id": grn.id,
            "grn_no": grn.grn_no,
            "lpo_no": lpo.lpo_no,
            "lpo_id": lpo.id,
            "supplier": supplier.description if supplier else "Unassigned",
            "invoice_ref": grn.invoice_ref or "",
            "has_invoice": has_invoice,
            "delivery_note": grn.delivery_note_ref or "",
            "receipt_date": grn.receipt_date.strftime("%d %b %Y"),
            "received_by": grn.received_by_name,
            "supplier_rep": grn.supplier_rep_name or "",
            "amount": f"{amount:.2f}",
            "amount_raw": float(amount),
            "task_id": task.project_id,
            "has_voucher": pv is not None,
            "voucher_no": pv.pay_order_no if pv else "",
            "voucher_method": pv.get_payment_method_display() if pv else "",
            "voucher_amount": f"{pv.amount:.2f}" if pv else "",
            "can_raise_voucher": has_invoice and pv is None,
            "print_url": reverse("print_grn_view", args=[grn.id]),
            "print_notify_url": (
                reverse("print_grn_view", args=[grn.id])
                + "?print=1&notify_admin=1&back=gm"
            ),
            "voucher_view_url": (
                reverse("print_payment_voucher_view", args=[pv.id]) if pv else ""
            ),
            "voucher_print_url": (
                reverse("print_payment_voucher_view", args=[pv.id]) + "?print=1"
                if pv
                else ""
            ),
            "lines": [
                {
                    "rfq_no": ln.lpo_item.rfq_no or "",
                    "desc": ln.lpo_item.description,
                    "uom": ln.lpo_item.uom,
                    "qty": f"{ln.qty_received}",
                    "unit_price": f"{ln.lpo_item.unit_price:.2f}",
                    "line_total": f"{(ln.qty_received * ln.lpo_item.unit_price):.2f}",
                }
                for ln in grn.lines.all()
            ],
        })
    return rows


def _serialize_task_payment_vouchers(task, start_date=None, end_date=None):
    from django.urls import reverse

    if not task:
        return []

    qs = (
        PaymentOrder.objects.filter(grn__lpo__project_task=task)
        .select_related("grn__lpo__supplier", "grn__lpo", "grn", "source_bank")
        .order_by("-created_at")
    )
    if start_date:
        qs = qs.filter(created_at__date__gte=start_date)
    if end_date:
        qs = qs.filter(created_at__date__lte=end_date)

    rows = []
    for pv in qs:
        grn = pv.grn
        lpo = grn.lpo
        supplier = lpo.supplier
        rows.append({
            "id": pv.id,
            "pay_order_no": pv.pay_order_no,
            "grn_no": grn.grn_no,
            "grn_id": grn.id,
            "lpo_no": lpo.lpo_no,
            "supplier": supplier.description if supplier else "Unassigned",
            "invoice_ref": grn.invoice_ref or "",
            "amount": f"{pv.amount:.2f}",
            "amount_raw": float(pv.amount),
            "method": pv.get_payment_method_display(),
            "bank": pv.source_bank.description if pv.source_bank else "",
            "reference": pv.transfer_reference or pv.cheque_number or "",
            "date": timezone.localtime(pv.created_at).strftime("%d %b %Y"),
            "print_url": reverse("print_payment_voucher_view", args=[pv.id]),
            "print_bundle_url": (
                reverse("print_payment_voucher_view", args=[pv.id]) + "?print=1"
            ),
            "grn_print_url": reverse("print_grn_view", args=[grn.id]),
        })
    return rows


def _gm_disbursement_redirect(task, **query):
    from django.urls import reverse

    params = {"task_id": task.project_id, **query}
    qs = "&".join(f"{k}={v}" for k, v in params.items() if v not in (None, ""))
    return f"{reverse('gm_aie_disbursement')}?{qs}"


def _banks_select_data():
    return [
        {
            "id": b.bank_account_id,
            "label": f"{b.description} — A/C {b.account_number}",
        }
        for b in BankAccount.objects.all().order_by("bank_account_id")
    ]


def _gm_create_payment_voucher(request, active_task, task_caps=None):
    from django.db import transaction as db_transaction

    if task_caps and not task_caps.get("enable_supplier_pv"):
        messages.error(request, "Supplier payment vouchers are only for Major (LPO/GRN) tasks.")
        return redirect(_gm_disbursement_redirect(active_task, open_grn_period="1"))

    grn_id = request.POST.get("grn_id")
    grn = get_object_or_404(
        GRNTransaction.objects.select_related("lpo__project_task", "lpo__supplier"),
        id=grn_id,
        lpo__project_task=active_task,
    )
    period_from = (request.POST.get("period_from") or "").strip()
    period_to = (request.POST.get("period_to") or "").strip()
    gm_return = {
        "open_grn_period": "1",
        "period_from": period_from,
        "period_to": period_to,
    }

    if not (grn.invoice_ref or "").strip():
        messages.error(request, "Payment voucher requires a supplier invoice on the GRN.")
        return redirect(_gm_disbursement_redirect(active_task, **gm_return))

    existing = PaymentOrder.objects.filter(grn=grn).first()
    if existing:
        messages.warning(request, f"GRN {grn.grn_no} already has voucher {existing.pay_order_no}.")
        return redirect(_gm_disbursement_redirect(active_task, **gm_return))

    method = (request.POST.get("payment_method") or "").strip().upper()
    if method not in ("BANK", "CHQ"):
        messages.error(request, "Select Bank Transfer or Cheque payment method.")
        return redirect(_gm_disbursement_redirect(active_task, **gm_return))

    bank_id = (request.POST.get("source_bank_id") or "").strip()
    bank = BankAccount.objects.filter(bank_account_id=bank_id).first()
    if not bank:
        messages.error(request, "Select the Pioneer bank account for this payment.")
        return redirect(_gm_disbursement_redirect(active_task, **gm_return))

    transfer_ref = (request.POST.get("transfer_reference") or "").strip()
    cheque_no = (request.POST.get("cheque_number") or "").strip()
    if method == "BANK" and not transfer_ref:
        messages.error(request, "Enter the bank transfer reference.")
        return redirect(_gm_disbursement_redirect(active_task, **gm_return))
    if method == "CHQ" and not cheque_no:
        messages.error(request, "Enter the cheque number.")
        return redirect(_gm_disbursement_redirect(active_task, **gm_return))

    amount = _money(request.POST, "voucher_amount", str(_grn_receipt_amount(grn)))
    if amount <= 0:
        messages.error(request, "Payment amount must be greater than zero.")
        return redirect(_gm_disbursement_redirect(active_task, **gm_return))

    prepared_by = (request.POST.get("prepared_by_name") or "").strip()
    notes = (request.POST.get("payment_notes") or "").strip()

    try:
        with db_transaction.atomic():
            pv = PaymentOrder.objects.create(
                grn=grn,
                payment_method=method,
                source_bank=bank,
                amount=amount,
                transfer_reference=transfer_ref,
                cheque_number=cheque_no,
                payment_notes=notes,
                prepared_by_name=prepared_by,
            )
        messages.success(
            request,
            f"Payment voucher {pv.pay_order_no} raised for GRN {grn.grn_no} — "
            f"{pv.get_payment_method_display()} US$ {amount:.2f}.",
        )
        return redirect(
            reverse("print_payment_voucher_view", args=[pv.id]) + "?back=gm&print=1"
        )
    except Exception as e:
        messages.error(request, f"Payment voucher failed: {e}")
        return redirect(_gm_disbursement_redirect(active_task, **gm_return))


def _bid_eval_cancel_lpo(request, active_task):
    lpo_id = request.POST.get("lpo_id")
    lpo = get_object_or_404(LPOTransaction, id=lpo_id, project_task=active_task)
    if lpo.status == LPOTransaction.STATUS_CANCELLED:
        messages.warning(request, f"{lpo.lpo_no} is already cancelled.")
    else:
        lpo.status = LPOTransaction.STATUS_CANCELLED
        lpo.cancelled_at = timezone.now()
        lpo.save(update_fields=["status", "cancelled_at"])
        messages.success(request, f"{lpo.lpo_no} has been cancelled.")
    return redirect(f"{reverse('bid_evaluation_terminal')}?task_id={active_task.project_id}")


def _bid_eval_create_grn(request, active_task):
    from datetime import datetime
    from django.db import transaction

    lpo_id = request.POST.get("lpo_id")
    lpo = get_object_or_404(LPOTransaction, id=lpo_id, project_task=active_task)

    if lpo.status == LPOTransaction.STATUS_CANCELLED:
        messages.error(request, "Cannot record GRN against a cancelled LPO.")
        return redirect(f"{reverse('bid_evaluation_terminal')}?task_id={active_task.project_id}")

    receipt_date_raw = (request.POST.get("receipt_date") or "").strip()
    try:
        receipt_date = (
            datetime.strptime(receipt_date_raw, "%Y-%m-%d").date()
            if receipt_date_raw
            else timezone.localdate()
        )
    except ValueError:
        messages.error(request, "Invalid receipt date.")
        return redirect(f"{reverse('bid_evaluation_terminal')}?task_id={active_task.project_id}")

    received_by_name = (request.POST.get("received_by_name") or "").strip()
    if not received_by_name:
        messages.error(request, "Enter the name of the person receiving the goods.")
        return redirect(f"{reverse('bid_evaluation_terminal')}?task_id={active_task.project_id}")

    supplier_rep_name = (request.POST.get("supplier_rep_name") or "").strip()

    invoice_ref = (request.POST.get("invoice_ref") or "").strip()
    delivery_note_ref = (request.POST.get("delivery_note_ref") or "").strip()
    if not invoice_ref:
        messages.error(request, "Enter the supplier invoice number.")
        return redirect(f"{reverse('bid_evaluation_terminal')}?task_id={active_task.project_id}")

    line_payload = []
    for item in lpo.items.all():
        raw_qty = request.POST.get(f"grn_qty_{item.id}", "").strip()
        if not raw_qty:
            continue
        try:
            qty = Decimal(raw_qty)
        except Exception:
            messages.error(request, f"Invalid quantity for line: {item.description}")
            return redirect(f"{reverse('bid_evaluation_terminal')}?task_id={active_task.project_id}")
        if qty <= 0:
            continue
        remaining = item.qty - _lpo_item_received_qty(item)
        if qty > remaining:
            messages.error(
                request,
                f"Quantity for {item.description} exceeds remaining ({remaining}).",
            )
            return redirect(f"{reverse('bid_evaluation_terminal')}?task_id={active_task.project_id}")
        line_payload.append((item, qty))

    if not line_payload:
        messages.error(request, "Enter at least one line quantity to receive.")
        return redirect(f"{reverse('bid_evaluation_terminal')}?task_id={active_task.project_id}")

    try:
        with transaction.atomic():
            grn = GRNTransaction.objects.create(
                lpo=lpo,
                receipt_date=receipt_date,
                received_by=request.user,
                received_by_name=received_by_name,
                supplier_rep_name=supplier_rep_name,
                invoice_ref=invoice_ref,
                delivery_note_ref=delivery_note_ref,
            )
            total_qty = Decimal("0")
            for item, qty in line_payload:
                GRNItem.objects.create(grn=grn, lpo_item=item, qty_received=qty)
                total_qty += qty
            grn.qty_received = total_qty
            grn.save(update_fields=["qty_received"])
        messages.success(
            request,
            f"GRN {grn.grn_no} recorded — "
            f"{'partial' if grn.is_partial else 'full'} delivery for {lpo.lpo_no}. "
            "Print the signed acknowledgement for filing.",
        )
        return redirect(reverse("print_grn_view", args=[grn.id]))
    except Exception as e:
        messages.error(request, f"GRN save failed: {e}")

    return redirect(f"{reverse('bid_evaluation_terminal')}?task_id={active_task.project_id}")


def _build_grn_print_context(grn):
    lpo = grn.lpo
    task = lpo.project_task
    supplier = lpo.supplier

    receipt_lines = []
    for grn_line in grn.lines.select_related("lpo_item").all():
        item = grn_line.lpo_item
        cumulative = _lpo_item_received_qty(item)
        outstanding = max(item.qty - cumulative, Decimal("0"))
        line_total = grn_line.qty_received * item.unit_price
        receipt_lines.append({
            "rfq_no": item.rfq_no or "—",
            "description": item.description,
            "uom": item.uom,
            "ordered": item.qty,
            "this_receipt": grn_line.qty_received,
            "unit_price": f"{item.unit_price:.2f}",
            "line_total": f"{line_total:.2f}",
            "cumulative_received": cumulative,
            "outstanding": outstanding,
        })

    outstanding_lines = []
    for item in lpo.items.all():
        cumulative = _lpo_item_received_qty(item)
        outstanding = max(item.qty - cumulative, Decimal("0"))
        if outstanding > 0:
            outstanding_lines.append({
                "rfq_no": item.rfq_no or "—",
                "description": item.description,
                "uom": item.uom,
                "ordered": item.qty,
                "received": cumulative,
                "outstanding": outstanding,
            })

    is_full = _lpo_receipt_status(lpo) == "FULL"
    receipt_total = _grn_receipt_amount(grn)
    return {
        "grn": grn,
        "lpo": lpo,
        "task": task,
        "supplier": supplier,
        "receipt_lines": receipt_lines,
        "outstanding_lines": outstanding_lines,
        "receipt_total": f"{receipt_total:.2f}",
        "is_full_delivery": is_full,
        "is_partial_delivery": not is_full,
        "receipt_date_display": grn.receipt_date.strftime("%B %d, %Y"),
        "company_rep": grn.received_by_name,
        "supplier_rep": grn.supplier_rep_name or "________________________",
        "lpo_list_url": (
            reverse("bid_evaluation_terminal")
            + f"?task_id={task.project_id}&open_lpo_list=1"
        ),
    }


@login_required
def print_grn_view(request, grn_id):
    from .emails import send_grn_admin_copy

    grn = get_object_or_404(
        GRNTransaction.objects.select_related(
            "lpo__project_task",
            "lpo__supplier",
            "received_by",
        ).prefetch_related("lines__lpo_item"),
        id=grn_id,
    )
    context = _build_grn_print_context(grn)
    notify_admin = request.GET.get("notify_admin") == "1"
    auto_print = request.GET.get("print") == "1"
    back_to = request.GET.get("back", "")

    if notify_admin:
        session_key = f"grn_admin_notify_{grn.id}"
        if not request.session.get(session_key):
            if send_grn_admin_copy(grn, request, print_context=context):
                request.session[session_key] = True
                request.session.modified = True

    context["auto_print"] = auto_print
    context["back_to_gm"] = back_to == "gm"
    if back_to == "gm":
        task = context["task"]
        context["gm_back_url"] = (
            reverse("gm_aie_disbursement")
            + f"?task_id={task.project_id}&open_grn_period=1"
        )
    return render(request, "grn_print_template.html", context)


def _payment_voucher_back_url(task):
    from django.urls import reverse

    return (
        reverse("gm_aie_disbursement")
        + f"?task_id={task.project_id}&open_voucher_period=1"
    )


def _build_payment_voucher_context(pv):
    grn = pv.grn
    grn_ctx = _build_grn_print_context(grn)
    task = grn_ctx["task"]
    return {
        "voucher": pv,
        "grn": grn,
        "lpo": grn_ctx["lpo"],
        "task": task,
        "supplier": grn_ctx["supplier"],
        "amount": pv.amount,
        "receipt_lines": grn_ctx["receipt_lines"],
        "receipt_total": grn_ctx["receipt_total"],
        "back_url": _payment_voucher_back_url(task),
        "back_label": "Back to GM Disbursement",
    }


@login_required
def print_payment_voucher_view(request, voucher_id):
    pv = get_object_or_404(
        PaymentOrder.objects.select_related(
            "grn__lpo__project_task",
            "grn__lpo__supplier",
            "source_bank",
        ).prefetch_related("grn__lines__lpo_item"),
        id=voucher_id,
    )
    context = _build_payment_voucher_context(pv)
    context["auto_print"] = request.GET.get("print") == "1"
    return render(request, "payment_voucher_print.html", context)


@login_required
def bid_evaluation_terminal_view(request):
    tasks = ProjectTask.objects.all()
    active_task = _task_from_request(
        request, tasks, include_post=(request.method == "POST")
    )

    if not active_task:
        if request.method == "POST":
            messages.error(request, "Select a project task before saving bid evaluation.")
            return redirect(reverse("bid_evaluation_terminal"))
        suppliers = SupplierAccount.objects.all().order_by("description")
        budget_status = _build_task_budget_status(None)
        return render(request, "bid_evaluation.html", {
            "active_task": None,
            "tasks": tasks,
            "bom_items": [],
            "source_type": "BOM",
            "suppliers": suppliers,
            "budget": None,
            "budget_channel": {"budget": None, "channel": None, "label": ""},
            "lpos": [],
            "budget_status": budget_status,
            "lpos_data": [],
            "grns_data": [],
            "grn_count": 0,
            "task_actual_cost": "0.00",
        })

    suppliers = SupplierAccount.objects.all().order_by("description")
    bom_header = BOMHeader.objects.filter(task=active_task).first()
    bom_items = BOMItem.objects.filter(header=bom_header) if bom_header else BOMItem.objects.none()
    ro_items = RequisitionOrderItem.objects.filter(ro__task=active_task)

    source_type, final_items = "BOM", bom_items
    if ro_items.exists():
        source_type, final_items = "RO", ro_items
    elif bom_items.exists():
        source_type, final_items = "BOM", bom_items

    if request.method == "POST":
        action = request.POST.get("action", "")
        if action == "cancel_lpo":
            return _bid_eval_cancel_lpo(request, active_task)
        if action == "create_grn":
            return _bid_eval_create_grn(request, active_task)

        try:
            supplier_ids = [
                x.strip()
                for x in (request.POST.get("supplier_ids_csv") or "").split(",")
                if x.strip()
            ]
            if len(supplier_ids) < 2:
                raise ValueError("Select two suppliers in the vault (Supplier 1 and Supplier 2).")
            awarded_id = (request.POST.get("awarded_supplier_id") or supplier_ids[0]).strip()
            target_supplier = SupplierAccount.objects.get(supplier_id=awarded_id)

            rfq_ok, rfq_reason = _rfq_channel_allowed(active_task)
            if not rfq_ok:
                raise ValueError(rfq_reason)

            with transaction.atomic():
                budget = _save_task_budget(
                    active_task,
                    ProjectBudget.BUDGET_RFQ_LPO,
                    _money(request.POST, "budget-material_total_cost"),
                    _money(request.POST, "budget-labour_burden"),
                    _money(request.POST, "budget-misc_reserve"),
                    _money(
                        request.POST,
                        "budget-total_authorized_budget",
                        request.POST.get("grand_total", "0"),
                    ),
                    label=f"Project Budget — {active_task.project_id}",
                )

                lpo = LPOTransaction.objects.create(
                    project_task=active_task,
                    supplier=target_supplier,
                    total_amount=_money(request.POST, "lpo-total_amount", request.POST.get("grand_total", "0")),
                    supplier_contact=request.POST.get("supplier_contact_csv") or "",
                )

                items_json = request.POST.get("items_json_payload", "[]")
                try:
                    item_list = json.loads(items_json) if items_json.strip() else []
                except json.JSONDecodeError:
                    item_list = []

                for row in item_list:
                    qty = Decimal(str(row.get("qty") or 0))
                    price = Decimal(str(row.get("price") or 0))
                    LPOItem.objects.create(
                        lpo=lpo,
                        description=row.get("desc", ""),
                        uom=row.get("uom", "pcs"),
                        qty=qty,
                        unit_price=price,
                        total_price=qty * price,
                    )

            messages.success(request, "Budget and LPO committed successfully.")

            if request.POST.get("after_commit") == "disburse_memo":
                from urllib.parse import urlencode

                params = urlencode({
                    "winner": target_supplier.description,
                    "mat": str(budget.material_total_cost),
                    "labour": str(budget.labour_burden),
                    "misc": str(budget.misc_reserve),
                    "supplier_id": target_supplier.supplier_id,
                })
                return redirect(
                    reverse("procurement_authorization", kwargs={"task_id": active_task.project_id})
                    + "?"
                    + params
                )

            return redirect(
                f"/lpo-dispatch/?task_id={active_task.project_id}&supplier_id={target_supplier.supplier_id}"
            )
        except Exception as e:
            messages.error(request, f"Save failed: {e}")

    budget_status = _build_task_budget_status(active_task)
    lpos_data = _serialize_task_lpos(active_task)
    grns_data = _serialize_task_grns(active_task)
    banks_data = _banks_select_data()
    channel_info = _task_budget_channel_info(active_task)

    return render(request, "bid_evaluation.html", {
        "active_task": active_task,
        "tasks": ProjectTask.objects.all(),
        "bom_items": final_items,
        "source_type": source_type,
        "suppliers": suppliers,
        "budget": channel_info["budget"],
        "budget_channel": channel_info,
        "lpos": LPOTransaction.objects.filter(project_task=active_task)
        .select_related("supplier")
        .prefetch_related("items")
        .order_by("-date_issued"),
        "budget_status": budget_status,
        "lpos_data": lpos_data,
        "grns_data": grns_data,
        "grn_count": len(grns_data),
        "task_actual_cost": budget_status["used"],
    })
# ===============================================================================
def print_lpo_preview(request):
    """
    Captures sandbox dataset passed via URLSearchParams and renders the 
    official, print-ready Local Purchase Order Document layout as a consolidated budget.
    """
    from datetime import datetime

    # 1. Extract incoming dataset strings from evaluation terminal JavaScript
    project_id = request.GET.get('project_id', '1')
    description_str = request.GET.get('description', 'Pioneer Construction Execution')
    supplier_str = request.GET.get('supplier', 'PENDING SELECTION')
    
    # Grab the true accumulated evaluation grand total amount
    grand_total_val = request.GET.get('grand_total', '0.00')

    # 2. Package data structures to match exactly what procurement_lpo_view.html parses
    task_mock = {
        'project_id': project_id,
        'description': description_str
    }

    # Generate quick tracking numbers for the demo state
    timestamp = datetime.now().strftime("%Y%m%d")
    simulated_lpo_no = f"LPO-{timestamp}-DEMO"
    current_date = datetime.now().strftime("%B %d, %Y")

    # 3. Create a single mock row for the 'build' loop so it renders the gross budget cleanly
    build_mock = [
        {
            'description': f"Consolidated Budget Allocation for Task Reference: {project_id} ({description_str})",
            'qty': 1,
            'uom': "LOT"
        }
    ]

    context = {
        # Core document mappings
        'winning_supplier': supplier_str,
        'task': task_mock,
        'lpo_no': simulated_lpo_no,
        'date': current_date,
        
        # Inject our mock row to clear out the "No items bound" empty message layout
        'build': build_mock,
        
        # Financial strings mapping directly to the bottom total box
        'materials_total': grand_total_val.replace(',', ''), # Strip format commas for clean template formatting
        
        'is_demo': request.GET.get('is_demo', 'false') == 'true',
    }
    
    return render(request, 'procurement_lpo_view.html', context)
    
# ===========================================================================

def _budget_channel_label(channel):
    labels = {
        ProjectBudget.BUDGET_RFQ_LPO: "Project Budget",
        ProjectBudget.BUDGET_ADHOC_MISC: "Ad-Hoc Budget",
    }
    return labels.get(channel, channel or "Unknown")


def _task_budget_record(task):
    if not task:
        return None
    return ProjectBudget.objects.filter(task=task).first()


def _misc_channel_allowed(task):
    """Ad-hoc misc flow only when task is not on RFQ/LPO budget channel."""
    budget = _task_budget_record(task)
    if budget and budget.budget_type == ProjectBudget.BUDGET_RFQ_LPO:
        return False, (
            f"This task already uses {_budget_channel_label(ProjectBudget.BUDGET_RFQ_LPO)}. "
            "A task may only have one budget channel."
        )
    if LPOTransaction.objects.filter(project_task=task).exists():
        return False, (
            "This task already has project procurement (LPO) records. "
            "Ad-hoc purchase is not available on this task."
        )
    return True, ""


def _rfq_channel_allowed(task):
    """Bid evaluation / LPO flow only when task is not on Ad-Hoc budget channel."""
    budget = _task_budget_record(task)
    if budget and budget.budget_type == ProjectBudget.BUDGET_ADHOC_MISC:
        return False, (
            f"This task already uses {_budget_channel_label(ProjectBudget.BUDGET_ADHOC_MISC)}. "
            "A task may only have one budget channel."
        )
    if MiscPurchaseOrder.objects.filter(task=task).exists():
        return False, (
            "This task already has ad-hoc RO records. "
            "Bid evaluation / project budget is not available on this task."
        )
    if MiscRequisitionOrder.objects.filter(task=task).exists():
        return False, (
            "This task already has ad-hoc requisition orders. "
            "Bid evaluation / project budget is not available on this task."
        )
    return True, ""


def _task_budget_channel_info(task):
    budget = _task_budget_record(task)
    misc_ok, misc_block = _misc_channel_allowed(task)
    rfq_ok, rfq_block = _rfq_channel_allowed(task)
    channel = budget.budget_type if budget and budget.budget_type else None
    if not channel:
        if not misc_ok and rfq_ok:
            channel = ProjectBudget.BUDGET_RFQ_LPO
        elif misc_ok and not rfq_ok:
            channel = ProjectBudget.BUDGET_ADHOC_MISC
    return {
        "channel": channel,
        "label": _budget_channel_label(channel) if channel else "Not committed",
        "misc_allowed": misc_ok,
        "rfq_allowed": rfq_ok,
        "misc_block_reason": misc_block,
        "rfq_block_reason": rfq_block,
        "budget": budget,
    }


def _save_task_budget(task, budget_type, material, labour, misc, total, label=None):
    """Create/update the single task budget and enforce channel exclusivity."""
    if budget_type == ProjectBudget.BUDGET_ADHOC_MISC:
        allowed, reason = _misc_channel_allowed(task)
    else:
        allowed, reason = _rfq_channel_allowed(task)
    if not allowed:
        raise ValueError(reason)

    budget, _ = ProjectBudget.objects.get_or_create(
        task=task,
        defaults={
            "budget_label": label or f"Budget — {task.project_id}",
            "budget_type": budget_type,
            "total_authorized_budget": Decimal("0"),
        },
    )
    if budget.budget_type and budget.budget_type != budget_type:
        raise ValueError(
            f"Budget channel conflict: task is on {_budget_channel_label(budget.budget_type)}."
        )
    if budget.is_ceo_approved:
        raise ValueError(
            "Budget is CEO-locked. Line figures cannot be changed after AIE approval."
        )
    budget.budget_type = budget_type
    budget.budget_label = label or budget.budget_label
    budget.material_total_cost = material
    budget.labour_burden = labour
    budget.misc_reserve = misc
    budget.total_authorized_budget = total
    budget.save()
    return budget


def _misc_planned_budget(task):
    """Misc / ad-hoc authorized budget for audit and variance."""
    if not task:
        return Decimal("0.00")
    budget = _task_budget_record(task)
    if budget and budget.budget_type == ProjectBudget.BUDGET_ADHOC_MISC:
        if budget.total_authorized_budget and budget.total_authorized_budget > 0:
            return budget.total_authorized_budget
        material = budget.material_total_cost or Decimal("0.00")
        misc = budget.misc_reserve or Decimal("0.00")
        return material + misc if (material + misc) > 0 else Decimal("0.00")
    if budget and budget.budget_type == ProjectBudget.BUDGET_RFQ_LPO:
        return budget.misc_reserve or Decimal("0.00")
    return Decimal("120000.00")


def _misc_locked_total(task):
    """Funds already locked or disbursed on ad-hoc ROs (count each MPO once)."""
    if not task:
        return Decimal("0.00")
    return (
        MiscPurchaseOrder.objects.filter(
            task=task,
            funding_status__in=["LOCKED", "DISBURSED"],
        ).aggregate(t=Sum("total_amount"))["t"]
        or Decimal("0.00")
    )


def _misc_ro_status_css(status):
    return {
        "PENDING": "ro-status-pending",
        "SUBMITTED": "ro-status-submitted",
        "LOCKED": "ro-status-locked",
        "DISBURSED": "ro-status-disbursed",
        "RECONCILED": "ro-status-reconciled",
    }.get(status or "", "ro-status-default")


def _normalize_misc_qty(qty):
    """Whole-number quantity for ad-hoc RO lines and officer PV purchases."""
    q = Decimal(str(qty or 0))
    if q < 0:
        q = Decimal("0")
    return q.quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def _fmt_misc_qty(qty):
    """Display ad-hoc quantity without decimal places."""
    return str(int(_normalize_misc_qty(qty)))


def _misc_qty_raw(qty):
    """JSON-safe whole-number quantity for ad-hoc UI."""
    return int(_normalize_misc_qty(qty))


def _misc_item_qty_purchased(mpo_item):
    total = (
        AdHocOfficerPaymentVoucherLine.objects.filter(mpo_item=mpo_item)
        .aggregate(t=Sum("qty_purchased"))["t"]
    )
    return total or Decimal("0")


def _misc_mpo_all_lines_purchased(mpo):
    items = list(mpo.items.all())
    if not items:
        return False
    for item in items:
        if item.qty > _misc_item_qty_purchased(item):
            return False
    return True


def _misc_mark_mpo_disbursed_if_complete(mpo):
    if mpo.funding_status in ("LOCKED", "SUBMITTED") and _misc_mpo_all_lines_purchased(mpo):
        mpo.funding_status = "DISBURSED"
        mpo.save(update_fields=["funding_status"])


def _misc_mpo_purchase_status(mpo):
    """Return NONE, PARTIAL, or FULL based on officer PV lines vs RO items."""
    items = list(mpo.items.all())
    if not items:
        return "NONE"
    any_paid = False
    all_full = True
    for item in items:
        paid = _misc_item_qty_purchased(item)
        if paid > 0:
            any_paid = True
        if paid < item.qty:
            all_full = False
    if not any_paid:
        return "NONE"
    return "FULL" if all_full else "PARTIAL"


def _serialize_task_adhoc_ros_for_purchase(task):
    from django.urls import reverse

    if not task:
        return []

    purchasable_statuses = ("SUBMITTED", "LOCKED", "DISBURSED")
    rows = []
    baseline = _get_task_baseline_mpo(task)
    if not baseline:
        return rows
    mpo = (
        MiscPurchaseOrder.objects.filter(pk=baseline.pk)
        .prefetch_related("items", "officer_vouchers__lines__mpo_item")
        .first()
    )
    if not mpo:
        return rows
    mpo_list = [mpo]
    for mpo in mpo_list:
        purchases_by_item = defaultdict(list)
        for pv in mpo.officer_vouchers.all().order_by("created_at", "id"):
            pv_print = reverse("print_adhoc_officer_voucher_view", args=[pv.id])
            for ln in pv.lines.select_related("mpo_item").all():
                if ln.qty_purchased <= 0:
                    continue
                purchases_by_item[ln.mpo_item_id].append({
                    "voucher_no": pv.voucher_no,
                    "pv_id": pv.id,
                    "date": timezone.localtime(pv.created_at).strftime("%d %b %Y"),
                    "officer": pv.officer_name,
                    "qty": _misc_qty_raw(ln.qty_purchased),
                    "amount": f"{ln.line_total:.2f}",
                    "print_url": pv_print,
                })

        items = []
        has_remaining = False
        for idx, item in enumerate(mpo.items.all().order_by("id"), start=1):
            qty_ordered = item.qty
            qty_purchased = _misc_item_qty_purchased(item)
            qty_remaining = max(qty_ordered - qty_purchased, Decimal("0"))
            if qty_remaining > 0:
                has_remaining = True
            if qty_remaining <= 0 and qty_purchased > 0:
                line_status = "FULL"
            elif qty_purchased > 0:
                line_status = "PARTIAL"
            else:
                line_status = "NONE"
            items.append({
                "index": idx,
                "id": str(item.id),
                "description": item.description,
                "uom": item.uom,
                "qty_ordered": _fmt_misc_qty(qty_ordered),
                "qty_purchased": _fmt_misc_qty(qty_purchased),
                "qty_remaining": _fmt_misc_qty(qty_remaining),
                "qty_remaining_raw": _misc_qty_raw(qty_remaining),
                "qty_purchased_raw": _misc_qty_raw(qty_purchased),
                "qty_ordered_raw": _misc_qty_raw(qty_ordered),
                "unit_price": f"{item.unit_price:.2f}",
                "unit_price_raw": float(item.unit_price),
                "line_total": f"{item.total:.2f}",
                "line_status": line_status,
                "purchases": purchases_by_item.get(item.id, []),
            })
        vouchers = []
        for pv in mpo.officer_vouchers.all().order_by("-created_at"):
            vouchers.append({
                "id": pv.id,
                "voucher_no": pv.voucher_no,
                "officer_name": pv.officer_name,
                "amount": f"{pv.amount:.2f}",
                "method": pv.get_payment_method_display(),
                "date": pv.created_at.strftime("%d %b %Y"),
                "print_url": reverse("print_adhoc_officer_voucher_view", args=[pv.id]),
                "lines": [
                    {
                        "line_no": ln.line_no,
                        "desc": ln.mpo_item.description,
                        "qty": _fmt_misc_qty(ln.qty_purchased),
                        "balance": _fmt_misc_qty(ln.qty_balance),
                        "unit_price": f"{ln.unit_price:.2f}",
                        "line_total": f"{ln.line_total:.2f}",
                    }
                    for ln in pv.lines.select_related("mpo_item").all()
                ],
            })
        rows.append({
            "id": str(mpo.id),
            "ref": mpo.mpo_number or f"MPO-{str(mpo.id)[:8].upper()}",
            "status": mpo.funding_status,
            "status_label": mpo.get_funding_status_display(),
            "purchase_status": _misc_mpo_purchase_status(mpo),
            "amount": f"{mpo.total_amount:.2f}",
            "amount_raw": float(mpo.total_amount),
            "date": mpo.created_at.strftime("%d %b %Y"),
            "task_id": task.project_id,
            "can_purchase": mpo.funding_status in purchasable_statuses and has_remaining,
            "is_submitted_plus": mpo.funding_status in purchasable_statuses,
            "items": items,
            "vouchers": vouchers,
            "print_ro_url": (
                reverse("print_fluid_ro")
                + f"?task_id={task.project_id}&mpo_id={mpo.id}"
            ),
        })
    return rows


def _serialize_task_officer_vouchers(task, start_date=None, end_date=None):
    from django.urls import reverse

    if not task:
        return []

    qs = (
        AdHocOfficerPaymentVoucher.objects.filter(task=task)
        .select_related("mpo")
        .prefetch_related("lines__mpo_item")
        .order_by("-created_at")
    )
    if start_date:
        qs = qs.filter(created_at__date__gte=start_date)
    if end_date:
        qs = qs.filter(created_at__date__lte=end_date)

    rows = []
    for pv in qs:
        rows.append({
            "id": pv.id,
            "voucher_no": pv.voucher_no,
            "officer_name": pv.officer_name,
            "ro_ref": pv.mpo.mpo_number or f"MPO-{pv.mpo_id}",
            "amount": f"{pv.amount:.2f}",
            "method": pv.get_payment_method_display(),
            "date": timezone.localtime(pv.created_at).strftime("%d %b %Y"),
            "is_settled": pv.is_settled,
            "print_url": reverse("print_adhoc_officer_voucher_view", args=[pv.id]),
            "print_bundle_url": (
                reverse("print_adhoc_officer_voucher_view", args=[pv.id]) + "?print=1"
            ),
            "lines": [
                {
                    "desc": ln.mpo_item.description,
                    "qty": _fmt_misc_qty(ln.qty_purchased),
                    "unit_price": f"{ln.unit_price:.2f}",
                    "line_total": f"{ln.line_total:.2f}",
                }
                for ln in pv.lines.select_related("mpo_item").all()
            ],
        })
    return rows


def _gm_officer_pv_return(task, **query):
    return _gm_disbursement_redirect(
        task,
        open_adhoc_ro_period="1",
        **query,
    )


def _gm_create_officer_payment_voucher(request, active_task, task_caps):
    from django.db import transaction as db_transaction

    if not task_caps.get("enable_adhoc_ro"):
        messages.error(request, "Officer payment vouchers are only for Ad-Hoc tasks.")
        return redirect(_gm_disbursement_redirect(active_task))

    mpo_id = (request.POST.get("mpo_id") or "").strip()
    mpo = get_object_or_404(
        MiscPurchaseOrder.objects.prefetch_related("items"),
        id=mpo_id,
        task=active_task,
    )
    period_from = (request.POST.get("period_from") or "").strip()
    period_to = (request.POST.get("period_to") or "").strip()
    gm_return = {"period_from": period_from, "period_to": period_to}

    if mpo.funding_status not in ("SUBMITTED", "LOCKED", "DISBURSED"):
        messages.error(request, "Submit the RO before raising officer payment vouchers.")
        return redirect(_gm_officer_pv_return(active_task, **gm_return))

    officer_name = (request.POST.get("officer_name") or "").strip()
    if not officer_name:
        messages.error(request, "Enter the officer name (payee).")
        return redirect(_gm_officer_pv_return(active_task, **gm_return))

    method = (request.POST.get("payment_method") or "").strip().upper()
    if method not in ("CASH", "MPESA"):
        messages.error(request, "Select Cash or M-Pesa payment method.")
        return redirect(_gm_officer_pv_return(active_task, **gm_return))

    mpesa_ref = (request.POST.get("mpesa_reference") or "").strip()
    if method == "MPESA" and not mpesa_ref:
        messages.error(request, "Enter the M-Pesa transaction reference.")
        return redirect(_gm_officer_pv_return(active_task, **gm_return))

    gm_name = (request.POST.get("gm_authority_name") or "").strip()
    if not gm_name:
        messages.error(request, "Enter the General Manager name as signing authority.")
        return redirect(_gm_officer_pv_return(active_task, **gm_return))

    prepared_by = (request.POST.get("prepared_by_name") or "").strip()
    notes = (request.POST.get("payment_notes") or "").strip()

    lines_json = request.POST.get("purchase_lines_json", "[]")
    try:
        line_payload = json.loads(lines_json) if lines_json.strip() else []
    except json.JSONDecodeError:
        line_payload = []

    if not line_payload:
        messages.error(request, "Select at least one RO line with quantity to purchase.")
        return redirect(_gm_officer_pv_return(active_task, **gm_return))

    item_map = {str(i.id): i for i in mpo.items.all()}
    parsed_lines = []
    total_amount = Decimal("0")

    for row in line_payload:
        item_id = str(row.get("item_id", "")).strip()
        try:
            qty_buy = _normalize_misc_qty(row.get("qty_purchase", 0))
        except Exception:
            qty_buy = Decimal("0")
        if qty_buy <= 0:
            continue
        item = item_map.get(item_id)
        if not item:
            raise ValueError(f"Invalid line item on RO {mpo.mpo_number}.")
        remaining = item.qty - _misc_item_qty_purchased(item)
        if qty_buy > remaining:
            raise ValueError(
                f"Cannot purchase {qty_buy} of {item.description}; only {remaining} remaining on RO."
            )
        line_total = qty_buy * item.unit_price
        line_no = int(row.get("line_no") or 0)
        qty_balance = remaining - qty_buy
        parsed_lines.append((item, qty_buy, item.unit_price, line_total, line_no, qty_balance))
        total_amount += line_total

    if not parsed_lines:
        messages.error(request, "Enter a purchase quantity greater than zero for at least one line.")
        return redirect(_gm_officer_pv_return(active_task, **gm_return))

    try:
        with db_transaction.atomic():
            pv = AdHocOfficerPaymentVoucher.objects.create(
                mpo=mpo,
                task=active_task,
                officer_name=officer_name,
                payment_method=method,
                mpesa_reference=mpesa_ref if method == "MPESA" else "",
                amount=total_amount,
                gm_authority_name=gm_name,
                prepared_by_name=prepared_by,
                payment_notes=notes,
                created_by=request.user,
            )
            for item, qty_buy, unit_price, line_total, line_no, qty_balance in parsed_lines:
                AdHocOfficerPaymentVoucherLine.objects.create(
                    voucher=pv,
                    mpo_item=item,
                    line_no=line_no,
                    qty_purchased=qty_buy,
                    qty_balance=qty_balance,
                    unit_price=unit_price,
                    line_total=line_total,
                )
            _misc_mark_mpo_disbursed_if_complete(mpo)
    except ValueError as e:
        messages.error(request, str(e))
        return redirect(_gm_officer_pv_return(active_task, **gm_return))
    except Exception as e:
        messages.error(request, f"Could not issue officer payment voucher: {e}")
        return redirect(_gm_officer_pv_return(active_task, **gm_return))

    messages.success(
        request,
        f"Officer PV {pv.voucher_no} — {fmt_money(total_amount)} advanced to {officer_name}.",
    )
    return redirect(
        reverse("print_adhoc_officer_voucher_view", args=[pv.id]) + "?print=1"
    )


def _gm_settle_officer_payment_voucher(request, active_task, task_caps):
    if not task_caps.get("enable_officer_pv"):
        messages.error(request, "Officer PV accounting is only for Ad-Hoc tasks.")
        return redirect(_gm_disbursement_redirect(active_task, open_officer_pv_period="1"))

    pv_id = (request.POST.get("voucher_id") or "").strip()
    pv = get_object_or_404(
        AdHocOfficerPaymentVoucher.objects.select_related("mpo"),
        id=pv_id,
        task=active_task,
    )
    period_from = (request.POST.get("period_from") or "").strip()
    period_to = (request.POST.get("period_to") or "").strip()
    gm_return = {
        "open_officer_pv_period": "1",
        "period_from": period_from,
        "period_to": period_to,
    }

    if pv.is_settled:
        messages.warning(request, f"{pv.voucher_no} is already accounted for.")
        return redirect(_gm_disbursement_redirect(active_task, **gm_return))

    actual_spent = _money(request.POST, "actual_spent", "0")
    change_returned = _money(request.POST, "change_returned", "0")
    receipt_ref = (request.POST.get("purchase_receipt_ref") or "").strip()
    settled_by = (request.POST.get("settled_by_name") or "").strip()

    if actual_spent <= 0:
        messages.error(request, "Enter the actual amount spent on the purchase.")
        return redirect(_gm_disbursement_redirect(active_task, **gm_return))
    if not receipt_ref:
        messages.error(request, "Enter the supplier purchase receipt reference.")
        return redirect(_gm_disbursement_redirect(active_task, **gm_return))
    if not settled_by:
        messages.error(request, "Enter who received the receipt and change.")
        return redirect(_gm_disbursement_redirect(active_task, **gm_return))

    if abs(actual_spent + change_returned - pv.amount) > Decimal("0.01"):
        messages.error(
            request,
            f"Actual spent ({fmt_money(actual_spent)}) plus change returned "
            f"({fmt_money(change_returned)}) must equal the advance "
            f"({fmt_money(pv.amount)}).",
        )
        return redirect(_gm_disbursement_redirect(active_task, **gm_return))

    pv.actual_spent = actual_spent
    pv.change_returned = change_returned
    pv.purchase_receipt_ref = receipt_ref
    pv.settled_by_name = settled_by
    pv.settled_at = timezone.now()
    pv.save(
        update_fields=[
            "actual_spent",
            "change_returned",
            "purchase_receipt_ref",
            "settled_by_name",
            "settled_at",
        ]
    )
    messages.success(
        request,
        f"{pv.voucher_no} accounted — {pv.officer_name}: spent {fmt_money(actual_spent)}, "
        f"change {fmt_money(change_returned)}.",
    )
    return redirect(_gm_disbursement_redirect(active_task, **gm_return))


def _misc_create_officer_payment_voucher(request, active_task):
    from django.db import transaction as db_transaction
    from django.urls import reverse

    mpo_id = (request.POST.get("mpo_id") or "").strip()
    mpo = get_object_or_404(
        MiscPurchaseOrder.objects.prefetch_related("items"),
        id=mpo_id,
        task=active_task,
    )

    if mpo.funding_status not in ("SUBMITTED", "LOCKED", "DISBURSED"):
        messages.error(
            request,
            "Submit the RO before raising officer payment vouchers.",
        )
        return redirect(
            reverse("gm_aie_disbursement")
            + f"?task_id={active_task.project_id}&open_adhoc_ro_period=1"
        )

    officer_name = (request.POST.get("officer_name") or "").strip()
    if not officer_name:
        messages.error(request, "Enter the receiving officer name.")
        return redirect(
            reverse("gm_aie_disbursement")
            + f"?task_id={active_task.project_id}&open_adhoc_ro_period=1"
        )

    method = (request.POST.get("payment_method") or "").strip().upper()
    if method not in ("CASH", "MPESA"):
        messages.error(request, "Select Cash or M-Pesa payment method.")
        return redirect(
            reverse("gm_aie_disbursement")
            + f"?task_id={active_task.project_id}&open_adhoc_ro_period=1"
        )

    mpesa_ref = (request.POST.get("mpesa_reference") or "").strip()
    if method == "MPESA" and not mpesa_ref:
        messages.error(request, "Enter the M-Pesa transaction reference.")
        return redirect(
            reverse("gm_aie_disbursement")
            + f"?task_id={active_task.project_id}&open_adhoc_ro_period=1"
        )

    gm_name = (request.POST.get("gm_authority_name") or "").strip()
    if not gm_name:
        messages.error(request, "Enter the General Manager name as signing authority.")
        return redirect(
            reverse("gm_aie_disbursement")
            + f"?task_id={active_task.project_id}&open_adhoc_ro_period=1&ro_detail={mpo_id}"
        )
    prepared_by = (request.POST.get("prepared_by_name") or "").strip()
    notes = (request.POST.get("payment_notes") or "").strip()

    lines_json = request.POST.get("purchase_lines_json", "[]")
    try:
        line_payload = json.loads(lines_json) if lines_json.strip() else []
    except json.JSONDecodeError:
        line_payload = []

    if not line_payload:
        messages.error(request, "Select at least one line with quantity to purchase.")
        return redirect(
            reverse("gm_aie_disbursement")
            + f"?task_id={active_task.project_id}&open_adhoc_ro_period=1"
        )

    item_map = {str(i.id): i for i in mpo.items.all()}
    parsed_lines = []
    total_amount = Decimal("0")

    for row in line_payload:
        item_id = str(row.get("item_id", "")).strip()
        qty_raw = row.get("qty_purchase", 0)
        try:
            qty_buy = _normalize_misc_qty(qty_raw)
        except Exception:
            qty_buy = Decimal("0")
        if qty_buy <= 0:
            continue
        item = item_map.get(item_id)
        if not item:
            raise ValueError(f"Invalid line item on RO {mpo.mpo_number}.")
        remaining = item.qty - _misc_item_qty_purchased(item)
        if qty_buy > remaining:
            raise ValueError(
                f"Cannot purchase {qty_buy} of {item.description}; only {remaining} remaining on RO."
            )
        line_total = qty_buy * item.unit_price
        line_no = int(row.get("line_no") or 0)
        qty_balance = remaining - qty_buy
        parsed_lines.append((item, qty_buy, item.unit_price, line_total, line_no, qty_balance))
        total_amount += line_total

    if not parsed_lines:
        messages.error(request, "Enter a purchase quantity greater than zero for at least one line.")
        return redirect(
            reverse("gm_aie_disbursement")
            + f"?task_id={active_task.project_id}&open_adhoc_ro_period=1"
        )

    try:
        with db_transaction.atomic():
            pv = AdHocOfficerPaymentVoucher.objects.create(
                mpo=mpo,
                task=active_task,
                officer_name=officer_name,
                payment_method=method,
                mpesa_reference=mpesa_ref if method == "MPESA" else "",
                amount=total_amount,
                gm_authority_name=gm_name,
                prepared_by_name=prepared_by,
                payment_notes=notes,
                created_by=request.user,
            )
            for item, qty_buy, unit_price, line_total, line_no, qty_balance in parsed_lines:
                AdHocOfficerPaymentVoucherLine.objects.create(
                    voucher=pv,
                    mpo_item=item,
                    line_no=line_no,
                    qty_purchased=qty_buy,
                    qty_balance=qty_balance,
                    unit_price=unit_price,
                    line_total=line_total,
                )
            _misc_mark_mpo_disbursed_if_complete(mpo)
    except ValueError as e:
        messages.error(request, str(e))
        return redirect(
            reverse("gm_aie_disbursement")
            + f"?task_id={active_task.project_id}&open_adhoc_ro_period=1"
        )
    except Exception as e:
        messages.error(request, f"Could not issue officer payment voucher: {e}")
        return redirect(
            reverse("gm_aie_disbursement")
            + f"?task_id={active_task.project_id}&open_adhoc_ro_period=1"
        )

    messages.success(
        request,
        f"Officer payment voucher {pv.voucher_no} issued for {fmt_money(total_amount)} to {officer_name}.",
    )
    return redirect(
        reverse("print_adhoc_officer_voucher_view", args=[pv.id])
        + f"?return_ro={mpo.id}"
    )


@login_required
def print_adhoc_officer_voucher_view(request, voucher_id):
    from django.urls import reverse

    pv = get_object_or_404(
        AdHocOfficerPaymentVoucher.objects.select_related("mpo", "task").prefetch_related(
            "lines__mpo_item"
        ),
        id=voucher_id,
    )
    return_ro = request.GET.get("return_ro") or str(pv.mpo_id)
    purchase_lines = []
    for idx, ln in enumerate(
        pv.lines.select_related("mpo_item").all().order_by("line_no", "id"),
        start=1,
    ):
        purchase_lines.append({
            "line_no": ln.line_no or idx,
            "description": ln.mpo_item.description,
            "uom": ln.mpo_item.uom,
            "qty_ro": _fmt_misc_qty(ln.mpo_item.qty),
            "qty": _fmt_misc_qty(ln.qty_purchased),
            "qty_balance": _fmt_misc_qty(ln.qty_balance),
            "unit_price": ln.unit_price,
            "line_total": ln.line_total,
        })
    context = {
        "voucher": pv,
        "mpo": pv.mpo,
        "task": pv.task,
        "purchase_lines": purchase_lines,
        "ro_list_url": (
            reverse("gm_aie_disbursement")
            + f"?task_id={pv.task.project_id}&open_adhoc_ro_period=1&ro_detail={return_ro}"
        ),
    }
    return render(request, "adhoc_officer_voucher_print.html", context)


def _misc_doc_return_url(task, *, audit=False):
    if audit:
        return reverse("misc_budget_actuals") + f"?task_id={task.project_id}"
    return reverse("misc_purchase_builder") + f"?task_id={task.project_id}&ro_list=1"


def _misc_mro_document_urls(mro, task, *, audit=False):
    from urllib.parse import quote

    ret = quote(_misc_doc_return_url(task, audit=audit), safe="")
    base = reverse("print_mro", kwargs={"mro_id": mro.id})
    pdf_base = reverse("print_mro_pdf", kwargs={"mro_id": mro.id})
    return {
        "mro_id": str(mro.id),
        "screen_url": f"{base}?return={ret}",
        "print_url": f"{pdf_base}?return={ret}",
        "pdf_url": f"{pdf_base}?return={ret}",
    }


def _misc_mpo_ro_document_urls(mpo, task, *, audit=False):
    from urllib.parse import quote

    ret = quote(_misc_doc_return_url(task, audit=audit), safe="")
    base = (
        reverse("print_fluid_ro")
        + f"?task_id={task.project_id}&mpo_id={mpo.id}&return={ret}"
    )
    pdf_base = reverse("print_mpo_pdf", kwargs={"mpo_id": mpo.id})
    return {
        "mro_id": "",
        "screen_url": base,
        "print_url": f"{pdf_base}?return={ret}",
        "pdf_url": f"{pdf_base}?return={ret}",
    }


def _misc_adhoc_ro_listing(task, active_mpo=None):
    """One sidebar row — the task's single ad-hoc RO/MRO baseline."""
    rows = []
    baseline = _get_task_baseline_mpo(task)
    if not baseline:
        return rows
    active_id = str(active_mpo.id) if active_mpo else None
    committed = getattr(baseline, "committed_mro", None)
    ref = baseline.mpo_number or f"MPO-{str(baseline.id)[:8].upper()}"
    if committed and committed.mro_number:
        ref = f"{ref} / {committed.mro_number}"
    row = {
        "id": str(baseline.id),
        "ref": ref,
        "status": baseline.funding_status,
        "status_label": baseline.get_funding_status_display()
        if hasattr(baseline, "get_funding_status_display")
        else baseline.funding_status,
        "amount": baseline.total_amount,
        "date": baseline.created_at,
        "kind": "MRO" if committed else "RO",
        "is_active": active_id == str(baseline.id),
        "status_class": _misc_ro_status_css(baseline.funding_status),
    }
    if committed:
        row.update(_misc_mro_document_urls(committed, task))
    else:
        row.update(_misc_mpo_ro_document_urls(baseline, task))
    rows.append(row)
    return rows


def _misc_task_mro_registry(task):
    """All ad-hoc MRO/MPO records for audit listing and deep links."""
    rows = []
    if not task:
        return rows
    mpos = {
        str(m.id): m
        for m in MiscPurchaseOrder.objects.filter(task=task).order_by("-created_at")
    }
    mros = list(
        MiscRequisitionOrder.objects.filter(task=task)
        .select_related("source_mpo")
        .order_by("-updated_at")
    )
    seen_mpo = set()
    for mro in mros:
        mpo = mro.source_mpo if mro.source_mpo_id else None
        if mpo:
            seen_mpo.add(str(mpo.id))
        row = {
            "kind": "MRO",
            "ref": mro.mro_number or "PENDING",
            "mpo_ref": mpo.mpo_number if mpo else "",
            "status": mro.funding_status,
            "status_label": mro.get_funding_status_display(),
            "amount": mro.total_amount,
            "date": mro.updated_at,
            "mpo_id": str(mpo.id) if mpo else "",
            "view_url": (
                reverse("misc_purchase_builder")
                + f"?task_id={task.project_id}&mpo_id={mpo.id}"
                if mpo
                else reverse("misc_purchase_builder") + f"?task_id={task.project_id}"
            ),
            "status_class": _misc_ro_status_css(mro.funding_status),
        }
        row.update(_misc_mro_document_urls(mro, task, audit=True))
        rows.append(row)
    for mpo_id, mpo in mpos.items():
        if mpo_id in seen_mpo:
            continue
        row = {
            "kind": "RO",
            "ref": mpo.mpo_number or f"MPO-{mpo_id[:8].upper()}",
            "mpo_ref": mpo.mpo_number or "",
            "status": mpo.funding_status,
            "status_label": mpo.get_funding_status_display(),
            "amount": mpo.total_amount,
            "date": mpo.created_at,
            "mpo_id": mpo_id,
            "view_url": reverse("misc_purchase_builder")
            + f"?task_id={task.project_id}&mpo_id={mpo_id}",
            "status_class": _misc_ro_status_css(mpo.funding_status),
        }
        row.update(_misc_mpo_ro_document_urls(mpo, task, audit=True))
        rows.append(row)
    rows.sort(key=lambda r: r["date"], reverse=True)
    return rows


def _misc_adhoc_actual_ro_total(task):
    """Sum of all ad-hoc RO material (draft, submitted, and committed) — one row per MPO."""
    if not task:
        return Decimal("0.00")
    return (
        MiscPurchaseOrder.objects.filter(
            task=task,
            funding_status__in=["PENDING", "SUBMITTED", "LOCKED", "DISBURSED"],
        ).aggregate(t=Sum("total_amount"))["t"]
        or Decimal("0.00")
    )


def _misc_adhoc_material_budget_status(task):
    """Ad-hoc material line vs RO actual total and variance (separate from RFQ/LPO budget)."""
    budget = _task_budget_record(task)
    if budget and budget.budget_type == ProjectBudget.BUDGET_ADHOC_MISC:
        material = budget.material_total_cost
    elif budget and budget.budget_type == ProjectBudget.BUDGET_RFQ_LPO:
        material = Decimal("0.00")
    else:
        material = Decimal("0.00")
    actual = _misc_adhoc_actual_ro_total(task)
    variance = material - actual
    return {
        "material": material,
        "actual_ro_total": actual,
        "variance": variance,
        "variance_over": variance < 0,
        "has_budget": budget is not None,
    }


def _misc_budget_formulation(
    task,
    project_budget,
    display_mpo,
    ro_mode,
    live_ro_material,
    draft_actual,
    has_committed,
    baseline_mro=None,
):
    """Budget card — committed figures when MRO exists; else live provisional from the baseline RO."""
    draft_actual = draft_actual or Decimal("0.00")
    labour = Decimal("0.00")
    misc = Decimal("0.00")
    readonly = False
    provisional_ref = ""
    source = "draft"
    mro = baseline_mro or _get_task_baseline_mro(task)

    if has_committed and project_budget and mro:
        material = project_budget.material_total_cost or Decimal("0.00")
        labour = project_budget.labour_burden or Decimal("0.00")
        misc = project_budget.misc_reserve or Decimal("0.00")
        grand = project_budget.total_authorized_budget or (material + labour + misc)
        readonly = True
        source = "committed"
        provisional_ref = mro.mro_number or ""
        if mro.source_mpo and mro.source_mpo.mpo_number:
            provisional_ref = f"{mro.source_mpo.mpo_number} / {provisional_ref}"
    elif display_mpo:
        material = live_ro_material if live_ro_material else draft_actual
        if project_budget and project_budget.budget_type == ProjectBudget.BUDGET_ADHOC_MISC:
            labour = project_budget.labour_burden or Decimal("0.00")
            misc = project_budget.misc_reserve or Decimal("0.00")
        grand = material + labour + misc
        readonly = _mpo_ro_locked(display_mpo)
        source = "provisional" if not mro else "ro"
        if display_mpo.mpo_number:
            provisional_ref = display_mpo.mpo_number
    else:
        material = draft_actual
        if project_budget and project_budget.budget_type == ProjectBudget.BUDGET_ADHOC_MISC:
            labour = project_budget.labour_burden or Decimal("0.00")
            misc = project_budget.misc_reserve or Decimal("0.00")
        grand = material + labour + misc

    return {
        "material": material,
        "labour": labour,
        "misc": misc,
        "grand": grand,
        "readonly": readonly,
        "provisional_ref": provisional_ref,
        "source": source,
    }


def _misc_ceo_payment_voucher_gate(task):
    """Officer PVs on GM Desk only after CEO AIE approval and fund release."""
    budget = _task_budget_record(task)
    approved = bool(budget and budget.is_ceo_approved)
    released = CEOFundRelease.objects.filter(task=task).exists()
    if not budget:
        message = (
            "Officer payment vouchers are not raised on this page. "
            "After the MRO baseline is confirmed, CEO must approve the provision budget (AIE) "
            "and disburse funds to GM Accounting — then raise vouchers at GM Disbursement desk."
        )
        stage = "no_budget"
    elif not approved:
        message = (
            "Payment vouchers cannot be raised yet. "
            "CEO must approve the provision budget (AIE) before GM can issue officer payment vouchers."
        )
        stage = "pending_ceo"
    elif not released:
        message = (
            "Payment vouchers cannot be raised yet. "
            "CEO must release funds to GM Accounting before officer payment vouchers can be issued."
        )
        stage = "pending_release"
    else:
        message = (
            "CEO has approved the budget and disbursed funds to GM Accounting. "
            "Raise officer payment vouchers (cash / M-Pesa) at the GM Disbursement desk."
        )
        stage = "ready"
    return {
        "can_raise_pv": approved and released,
        "is_ceo_approved": approved,
        "fund_released": released,
        "message": message,
        "stage": stage,
    }


def _get_task_baseline_mro(task):
    """Single ad-hoc MRO baseline per task (budget anchor)."""
    if not task:
        return None
    return (
        MiscRequisitionOrder.objects.filter(task=task)
        .select_related("source_mpo")
        .order_by("created_at")
        .first()
    )


def _get_task_baseline_mpo(task):
    """Single ad-hoc RO/MPO per task — linked MPO when MRO exists, else the lone MPO."""
    if not task:
        return None
    mro = _get_task_baseline_mro(task)
    if mro and mro.source_mpo_id:
        return (
            MiscPurchaseOrder.objects.filter(pk=mro.source_mpo_id)
            .select_related("committed_mro")
            .first()
        )
    return (
        MiscPurchaseOrder.objects.filter(task=task)
        .select_related("committed_mro")
        .order_by("created_at")
        .first()
    )


def _task_has_adhoc_baseline(task):
    return _get_task_baseline_mpo(task) is not None


def _misc_default_gl():
    return GLAccount.objects.first()


def _ensure_mpo_reference(mpo):
    """Assign the permanent Misc RO number when the officer locks the grand total."""
    if not mpo.mpo_number:
        mpo.mpo_number = _next_mpo_number()
        mpo.save(update_fields=["mpo_number"])
    return mpo.mpo_number


def _get_active_draft_mpo(task):
    """Editable or locked-but-not-submitted draft on the workspace."""
    return (
        MiscPurchaseOrder.objects.filter(task=task, funding_status="PENDING")
        .order_by("-created_at")
        .first()
    )


def _get_or_create_draft_mpo(task, supplier_name=""):
    """One open PENDING MPO per task — persisted scouting basket with unique RO reference."""
    allowed, reason = _misc_channel_allowed(task)
    if not allowed:
        raise ValueError(reason)

    mpo = _get_active_draft_mpo(task)
    if not mpo:
        if _task_has_adhoc_baseline(task):
            baseline = _get_task_baseline_mpo(task)
            if baseline and baseline.funding_status == "PENDING":
                return baseline
            raise ValueError(
                "This task already has its ad-hoc baseline requisition. "
                "One budget and one MRO per task."
            )
        mpo = MiscPurchaseOrder.objects.create(
            task=task,
            funding_status="PENDING",
            is_sourcing=True,
            messenger_name=(supplier_name or "Officer purchase RO")[:100],
            total_amount=Decimal("0.00"),
        )
    else:
        if supplier_name:
            mpo.messenger_name = supplier_name[:100]
            mpo.save(update_fields=["messenger_name"])
    return mpo


def _recalc_mpo_total(mpo):
    total = mpo.items.aggregate(t=Sum("total"))["t"] or Decimal("0.00")
    mpo.total_amount = total
    mpo.save(update_fields=["total_amount"])
    return total


def _misc_supplier_session(request):
    data = request.session.get("misc_supplier")
    if not isinstance(data, dict):
        data = {}
    return data


def _save_misc_supplier_session(request, supplier=None, ad_hoc=None):
    """Persist selected DB supplier or ad-hoc vendor details in session."""
    if supplier:
        request.session["misc_supplier"] = {
            "supplier_id": supplier.supplier_id,
            "name": supplier.description,
            "phone": supplier.phone or "",
            "email": supplier.email or "",
            "address": supplier.contact_address or "",
            "is_ad_hoc": False,
        }
    elif ad_hoc:
        request.session["misc_supplier"] = {
            "supplier_id": ad_hoc.get("supplier_id", ""),
            "name": ad_hoc.get("name", ""),
            "phone": ad_hoc.get("phone", ""),
            "email": ad_hoc.get("email", ""),
            "address": ad_hoc.get("address", ""),
            "is_ad_hoc": True,
        }
    request.session.modified = True


def _mpo_supplier_label(misc_sup):
    if not misc_sup:
        return ""
    if misc_sup.get("supplier_id") and not misc_sup.get("is_ad_hoc"):
        return f"{misc_sup.get('name', '')} (#{misc_sup['supplier_id']})"[:100]
    parts = [misc_sup.get("name") or "Ad-hoc vendor"]
    if misc_sup.get("phone"):
        parts.append(misc_sup["phone"])
    return " | ".join(parts)[:100]


def _apply_supplier_to_mpo(mpo, misc_sup):
    label = _mpo_supplier_label(misc_sup)
    if label:
        mpo.messenger_name = label
        mpo.save(update_fields=["messenger_name"])


def _mpo_to_batch(mpo, misc_sup=None):
    items = []
    for it in mpo.items.all().order_by("id"):
        items.append({
            "id": it.id,
            "description": it.description,
            "uom": getattr(it, "uom", None) or "EA",
            "qty": _misc_qty_raw(it.qty),
            "unit_price": float(it.unit_price),
            "total": float(it.total),
        })
    misc_sup = misc_sup or {}
    name = misc_sup.get("name") or mpo.messenger_name or ""
    return {
        "supplier": name,
        "supplier_id": misc_sup.get("supplier_id", ""),
        "supplier_phone": misc_sup.get("phone", ""),
        "supplier_email": misc_sup.get("email", ""),
        "supplier_address": misc_sup.get("address", ""),
        "is_ad_hoc": misc_sup.get("is_ad_hoc", False),
        "items": items,
        "draft_mpo_id": str(mpo.id),
    }


def _sync_session_from_mpo(request, active_task, mpo):
    misc_sup = _misc_supplier_session(request)
    batch = _mpo_to_batch(mpo, misc_sup)
    request.session["batch_data"] = batch
    request.session["active_task_id"] = active_task.project_id
    request.session.modified = True
    return batch


def _create_supplier_from_post(post):
    """Register a new supplier in SupplierAccount from modal/form."""
    supplier_id = (post.get("new_supplier_id") or post.get("supplier_id") or "").strip()
    if not supplier_id:
        supplier_id = f"ADH-{timezone.now().strftime('%y%m%d%H%M%S')}"
    if SupplierAccount.objects.filter(supplier_id=supplier_id).exists():
        raise ValueError(f"Supplier ID {supplier_id} already exists.")
    return SupplierAccount.objects.create(
        supplier_id=supplier_id,
        description=(post.get("description") or post.get("supplier_name") or "Ad-hoc Supplier")[:200],
        contact_address=post.get("contact_address") or post.get("supplier_address") or "—",
        phone=post.get("phone") or post.get("supplier_phone") or "—",
        email=post.get("email") or post.get("supplier_email") or "adhoc@pioneer.local",
        bank_account_number=post.get("bank_account_number") or "N/A",
    )


def _next_mpo_number():
    year = timezone.now().year
    last = (
        MiscPurchaseOrder.objects.filter(mpo_number__startswith=f"MPO-{year}-")
        .order_by("-mpo_number")
        .first()
    )
    seq = int(last.mpo_number.split("-")[-1]) + 1 if last and last.mpo_number else 1
    return f"MPO-{year}-{seq:04d}"


def _next_mro_number():
    year = timezone.now().year
    last = (
        MiscRequisitionOrder.objects.filter(mro_number__startswith=f"MRO-{year}-")
        .order_by("-mro_number")
        .first()
    )
    seq = int(last.mro_number.split("-")[-1]) + 1 if last and last.mro_number else 1
    return f"MRO-{year}-{seq:04d}"


@login_required
def misc_register_supplier_ajax(request):
    """AJAX: register supplier and return JSON for vault refresh."""
    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "POST required"}, status=405)
    try:
        supplier = _create_supplier_from_post(request.POST)
        _save_misc_supplier_session(request, supplier=supplier)
        return JsonResponse({
            "status": "success",
            "message": f"Supplier {supplier.supplier_id} registered.",
            "supplier": {
                "supplier_id": supplier.supplier_id,
                "description": supplier.description,
                "phone": supplier.phone,
                "email": supplier.email,
                "contact_address": supplier.contact_address,
            },
        })
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=400)


@login_required
def misc_purchase_builder(request):
    tasks, active_task = _resolve_misc_purchase_task(
        request, include_post=(request.method == "POST")
    )
    if not active_task:
        requested = _task_id_from_request(
            request, include_post=(request.method == "POST")
        )
        if requested:
            blocked_task = ProjectTask.objects.filter(project_id=requested).first()
            if blocked_task:
                allowed, reason = _misc_channel_allowed(blocked_task)
                if _task_on_major_bom_lane(blocked_task) or not allowed:
                    messages.error(
                        request,
                        reason
                        or "This task is not on the MRO path. Press Esc or return to the main menu.",
                    )
                    return redirect(reverse("ops_dashboard"))
        if request.method == "POST":
            messages.error(request, "Select a project task before saving.")
            return redirect(reverse("misc_purchase_builder"))
        if not tasks.exists():
            messages.info(
                request,
                "Add a project task from Dashboard setup before using Misc Purchase.",
            )
            return redirect("dashboard")
        first_adhoc = tasks.order_by("project_id").first()
        if requested and first_adhoc:
            messages.info(
                request,
                "Choose an MRO task from the list, or press Esc to return to the main menu.",
            )
            return redirect(
                reverse("misc_purchase_builder")
                + f"?task_id={first_adhoc.project_id}"
            )
        suppliers = SupplierAccount.objects.all().order_by("description")
        return render(request, "misc_purchase.html", {
            "tasks": tasks,
            "active_task": None,
            "mro_workspace_empty": False,
            "officer_journey_visible": False,
            "suppliers": suppliers,
            "no_task_selected": True,
        })

    suppliers = SupplierAccount.objects.all().order_by("description")

    default_gl = _misc_default_gl()
    if request.method != "POST":
        _prune_empty_numbered_draft_mpos(active_task)

    if request.method == "POST":
        if request.POST.get("action") == "create_officer_payment_voucher":
            messages.info(
                request,
                "Officer payment vouchers are raised on the GM Disbursement desk.",
            )
            return redirect(
                reverse("gm_aie_disbursement")
                + f"?task_id={active_task.project_id}&open_adhoc_ro_period=1"
            )

        if not default_gl and not (
            "select_supplier" in request.POST
            or "register_supplier" in request.POST
            or "save_ad_hoc_supplier" in request.POST
        ):
            messages.error(
                request,
                "No GL expense account in the system. Add a GL account before saving misc purchases.",
            )
            return redirect(f"/misc-purchase/?task_id={active_task.project_id}")

        try:
            with transaction.atomic():
                misc_sup = _misc_supplier_session(request)

                if "new_ro" in request.POST:
                    if _task_has_adhoc_baseline(active_task):
                        baseline = _get_task_baseline_mpo(active_task)
                        ref = baseline.mpo_number if baseline else "RO"
                        raise ValueError(
                            f"This task already has ad-hoc baseline {ref}. "
                            "One budget and one MRO per task â€” continue the existing requisition."
                        )
                    existing = _get_active_draft_mpo(active_task)
                    if existing:
                        if existing.items.exists() or not existing.is_sourcing:
                            ref = existing.mpo_number or f"MPO-{str(existing.id)[:8].upper()}"
                            raise ValueError(
                                f"Draft {ref} is still open â€” add lines, lock & submit it, "
                                f"or open it from RO List."
                            )
                        mpo = existing
                        messages.info(
                            request,
                            f"Continuing draft {existing.mpo_number} â€” add item lines (qty Â· price).",
                        )
                    else:
                        mpo = MiscPurchaseOrder.objects.create(
                            task=active_task,
                            funding_status="PENDING",
                            is_sourcing=True,
                            messenger_name="Officer purchase RO",
                            total_amount=Decimal("0.00"),
                        )
                        request.session.pop("misc_supplier", None)
                        messages.success(
                            request,
                            "RO started â€” add item lines (qty Â· price). "
                            "RO Number is assigned when the first line is saved.",
                        )
                    _sync_session_from_mpo(request, active_task, mpo)
                else:
                    mpo = _require_draft_mpo(active_task, "Officer purchase RO")

                    _MPO_EDIT_ACTIONS = (
                        "select_supplier",
                        "register_supplier",
                        "save_ad_hoc_supplier",
                        "update_supplier",
                        "add_misc_purchase",
                        "delete_item",
                    )
                    if any(k in request.POST for k in _MPO_EDIT_ACTIONS):
                        _assert_mpo_editable(mpo)

                    if "select_supplier" in request.POST:
                        sid = request.POST.get("supplier_id", "").strip()
                        supplier = SupplierAccount.objects.filter(supplier_id=sid).first()
                        if not supplier:
                            raise ValueError("Select a valid supplier from the vault.")
                        _save_misc_supplier_session(request, supplier=supplier)
                        _apply_supplier_to_mpo(mpo, _misc_supplier_session(request))
                        messages.success(request, f"Supplier locked: {supplier.description}")

                    elif "register_supplier" in request.POST:
                        supplier = _create_supplier_from_post(request.POST)
                        _save_misc_supplier_session(request, supplier=supplier)
                        _apply_supplier_to_mpo(mpo, _misc_supplier_session(request))
                        messages.success(request, f"New supplier registered: {supplier.supplier_id}")

                    elif "save_ad_hoc_supplier" in request.POST:
                        _save_misc_supplier_session(
                            request,
                            ad_hoc={
                                "supplier_id": "",
                                "name": request.POST.get("adhoc_name") or request.POST.get("supplier", ""),
                                "phone": request.POST.get("adhoc_phone", ""),
                                "email": request.POST.get("adhoc_email", ""),
                                "address": request.POST.get("adhoc_address", ""),
                            },
                        )
                        _apply_supplier_to_mpo(mpo, _misc_supplier_session(request))
                        messages.success(request, "Ad-hoc vendor details saved (not in supplier master).")

                    elif "update_supplier" in request.POST:
                        sid = request.POST.get("supplier_id", "").strip()
                        if sid:
                            supplier = SupplierAccount.objects.get(supplier_id=sid)
                            _save_misc_supplier_session(request, supplier=supplier)
                        else:
                            _save_misc_supplier_session(
                                request,
                                ad_hoc={
                                    "name": request.POST.get("supplier", ""),
                                    "phone": request.POST.get("supplier_phone", ""),
                                    "email": request.POST.get("supplier_email", ""),
                                    "address": request.POST.get("supplier_address", ""),
                                },
                            )
                        _apply_supplier_to_mpo(mpo, _misc_supplier_session(request))
                        messages.success(request, "Supplier updated on draft RO.")

                    elif "lock_ro_total" in request.POST:
                        if not mpo.items.exists():
                            raise ValueError("Add at least one line item before locking the RO total.")
                        if _mpo_ro_locked(mpo):
                            ref = (mpo.mpo_number or "").strip() or "Misc RO"
                            raise ValueError(f"{ref} is already locked.")
                        total = _recalc_mpo_total(mpo)
                        ref = _ensure_mpo_reference(mpo)
                        mpo.is_sourcing = False
                        mpo.save(update_fields=["is_sourcing", "total_amount"])
                        messages.success(
                            request,
                            f"Misc RO {ref} locked at {fmt_money(total)}. Submit the RO when ready.",
                        )

                    elif "submit_ro" in request.POST:
                        if not mpo.items.exists():
                            raise ValueError("Add at least one line item before submitting the RO.")
                        if mpo.is_sourcing:
                            raise ValueError("Lock the RO grand total before submitting.")
                        _ensure_mpo_reference(mpo)
                        total = _recalc_mpo_total(mpo)
                        mpo.funding_status = "SUBMITTED"
                        mpo.save(update_fields=["funding_status", "total_amount"])
                        request.session["batch_data"] = {"items": [], "supplier": ""}
                        request.session.modified = True
                        messages.success(
                            request,
                            f"RO {mpo.mpo_number} submitted â€” raise payment vouchers at GM Desk "
                            f"(Ad-Hoc Payment) for partial or full item purchase.",
                        )
                        return redirect(
                            f"/misc-purchase/?task_id={active_task.project_id}"
                        )

                    elif "add_misc_purchase" in request.POST:
                        if not mpo.is_sourcing:
                            raise ValueError("RO total is locked â€” remove lock is not allowed; submit or start a new RO.")
                        if not default_gl:
                            raise ValueError("Add a GL account before adding line items.")
                        qty = _normalize_misc_qty(request.POST.get("qty", 0) or 0)
                        price = Decimal(str(request.POST.get("unit_price", 0) or 0))
                        line_total = qty * price
                        MiscPurchaseItem.objects.create(
                            mpo=mpo,
                            task=active_task,
                            gl_expense_account=default_gl,
                            description=request.POST.get("description", ""),
                            uom=request.POST.get("uom", "EA")[:50],
                            qty=qty,
                            unit_price=price,
                            total=line_total,
                        )
                        _recalc_mpo_total(mpo)
                        messages.success(request, "Line item saved to database.")

                    elif "delete_item" in request.POST:
                        item_id = request.POST.get("item_id")
                        if item_id:
                            MiscPurchaseItem.objects.filter(
                                id=item_id, mpo=mpo, task=active_task
                            ).delete()
                        else:
                            idx = int(request.POST.get("index", 0))
                            lines = list(mpo.items.all().order_by("id"))
                            if 0 <= idx < len(lines):
                                lines[idx].delete()
                        _recalc_mpo_total(mpo)
                        messages.success(request, "Line item removed from database.")

                    _sync_session_from_mpo(request, active_task, mpo)
        except Exception as e:
            messages.error(request, f"Save failed: {e}")

        return redirect(f"/misc-purchase/?task_id={active_task.project_id}")

    view_mpo_id = request.GET.get("mpo_id")
    viewed_mpo = None
    baseline_mpo = _get_task_baseline_mpo(active_task)
    baseline_mro = _get_task_baseline_mro(active_task)
    task_has_baseline = _task_has_adhoc_baseline(active_task)

    if view_mpo_id:
        viewed_mpo = MiscPurchaseOrder.objects.filter(
            id=view_mpo_id, task=active_task
        ).first()
        if not viewed_mpo and baseline_mpo and str(baseline_mpo.id) == view_mpo_id:
            viewed_mpo = baseline_mpo
    elif baseline_mpo and (_mpo_has_ro_number(baseline_mpo) or _misc_display_mro_number(baseline_mro)):
        viewed_mpo = baseline_mpo

    draft_mpo = _get_active_draft_mpo(active_task) if not viewed_mpo else None
    misc_sup = _misc_supplier_session(request)

    if viewed_mpo:
        batch = _mpo_to_batch(viewed_mpo, misc_sup if viewed_mpo.funding_status == "PENDING" else {})
        if viewed_mpo.funding_status == "PENDING" and viewed_mpo.is_sourcing:
            ro_mode = "draft"
        elif viewed_mpo.funding_status == "PENDING":
            ro_mode = "locked"
        else:
            ro_mode = "detail"
        ro_locked = _mpo_ro_locked(viewed_mpo)
        ro_submitted = viewed_mpo.funding_status == "SUBMITTED"
    elif draft_mpo:
        batch = _mpo_to_batch(draft_mpo, misc_sup)
        _sync_session_from_mpo(request, active_task, draft_mpo)
        ro_mode = "locked" if _mpo_ro_locked(draft_mpo) else "draft"
        ro_locked = _mpo_ro_locked(draft_mpo)
        ro_submitted = False
    else:
        session_batch = request.session.get("batch_data") or {}
        batch = {
            "supplier": misc_sup.get("name", session_batch.get("supplier", "")),
            "supplier_id": misc_sup.get("supplier_id", ""),
            "supplier_phone": misc_sup.get("phone", ""),
            "supplier_email": misc_sup.get("email", ""),
            "supplier_address": misc_sup.get("address", ""),
            "is_ad_hoc": misc_sup.get("is_ad_hoc", False),
            "items": session_batch.get("items", []),
            "draft_mpo_id": "",
        }
        ro_mode = "empty"
        ro_locked = False
        ro_submitted = False

    display_mpo = viewed_mpo or draft_mpo
    can_review_budget = bool(
        display_mpo
        and display_mpo.items.exists()
        and not display_mpo.is_sourcing
        and display_mpo.funding_status in ("PENDING", "SUBMITTED")
    )
    draft_actual = sum(Decimal(str(i.get("total", 0))) for i in batch.get("items", []))
    if display_mpo and display_mpo.total_amount:
        live_ro_material = display_mpo.total_amount
    else:
        live_ro_material = draft_actual
    misc_budget = _misc_planned_budget(active_task)
    locked_total = _misc_locked_total(active_task)
    variance = misc_budget - draft_actual
    material_status = _misc_adhoc_material_budget_status(active_task)
    project_budget = _task_budget_record(active_task)
    has_committed_adhoc_material = bool(
        project_budget
        and project_budget.budget_type == ProjectBudget.BUDGET_ADHOC_MISC
        and (project_budget.material_total_cost or Decimal("0")) > 0
        and baseline_mro is not None
    )
    has_provisional_budget = bool(
        baseline_mpo
        and not has_committed_adhoc_material
        and (live_ro_material or draft_actual)
    )
    if has_committed_adhoc_material:
        sidebar_material = project_budget.material_total_cost
        sidebar_actual = material_status["actual_ro_total"]
    else:
        sidebar_material = live_ro_material
        sidebar_actual = live_ro_material
    sidebar_variance = sidebar_material - sidebar_actual
    sidebar_variance_over = sidebar_variance < 0
    budget_status = _build_task_budget_status(active_task)
    channel_info = _task_budget_channel_info(active_task)

    budget_formulation = _misc_budget_formulation(
        active_task,
        project_budget,
        display_mpo,
        ro_mode,
        live_ro_material,
        draft_actual,
        has_committed_adhoc_material,
        baseline_mro=baseline_mro,
    )
    show_review_budget = bool(can_review_budget) and not has_committed_adhoc_material
    pv_gate = _misc_ceo_payment_voucher_gate(active_task)
    batch_item_count = (
        display_mpo.items.count()
        if display_mpo
        else len(batch.get("items") or [])
    )
    officer_journey_visible = _misc_stage_b_onboarding_visible(
        active_task,
        ro_mode=ro_mode,
        batch_item_count=batch_item_count,
        ro_locked=ro_locked,
        task_has_baseline=task_has_baseline,
    )
    mro_workspace_empty = officer_journey_visible

    return render(
        request,
        "misc_purchase.html",
        {
            "tasks": tasks,
            "active_task": active_task,
            "mro_workspace_empty": mro_workspace_empty,
            "officer_journey_visible": officer_journey_visible,
            "batch": batch,
            "budget_x": misc_budget,
            "misc_budget": misc_budget,
            "actual": budget_formulation["material"],
            "locked_total": locked_total,
            "variance": variance,
            "variance_over": variance < 0,
            "has_budget": ProjectBudget.objects.filter(task=active_task).exists(),
            "draft_mpo": draft_mpo,
            "viewed_mpo": viewed_mpo,
            "display_mpo": display_mpo,
            "ro_mode": ro_mode,
            "ro_locked": ro_locked,
            "ro_submitted": ro_submitted,
            "ro_list_open": request.GET.get("ro_list") == "1",
            "pv_gate": pv_gate,
            "can_review_budget": can_review_budget,
            "show_review_budget": show_review_budget,
            "budget_formulation": budget_formulation,
            "formulation_material": budget_formulation["material"],
            "formulation_labour": budget_formulation["labour"],
            "formulation_misc": budget_formulation["misc"],
            "formulation_grand": budget_formulation["grand"],
            "formulation_readonly": budget_formulation["readonly"],
            "provisional_budget_ref": budget_formulation["provisional_ref"],
            "suppliers": suppliers,
            "adhoc_ro_listing": _misc_adhoc_ro_listing(active_task, display_mpo),
            "task_has_baseline": task_has_baseline,
            "baseline_mro": baseline_mro,
            "baseline_mro_ref": _misc_display_mro_number(baseline_mro),
            "mro_number": _misc_display_mro_number(baseline_mro),
            "ro_number": _misc_display_ro_number(display_mpo) if display_mpo else "",
            "has_provisional_budget": has_provisional_budget,
            "budget_formulation_source": budget_formulation["source"],
            "material_budget": sidebar_material,
            "ro_actual_total": sidebar_actual,
            "material_variance": sidebar_variance,
            "material_variance_over": sidebar_variance_over,
            "live_ro_material": live_ro_material,
            "adhoc_material_committed": has_committed_adhoc_material,
            "has_material_budget": material_status["has_budget"],
            "budget_status": budget_status,
            "seed_labour": budget_formulation["labour"],
            "seed_misc": budget_formulation["misc"],
            "budget_channel": channel_info,
            "ro_reference": _misc_display_ro_number(display_mpo) if display_mpo else "",
        },
    )
    
# =================================================================

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.utils import timezone
# from .models import ProjectTask, MiscPurchaseOrder, MiscPurchaseItem

@login_required
def ad_hoc_purchase_memo_view(request):
    """Executive memo from the PENDING draft stored in the database."""
    target_task_id = request.GET.get("task_id")
    active_task = get_object_or_404(ProjectTask, project_id=target_task_id)
    draft_mpo = MiscPurchaseOrder.objects.filter(
        task=active_task, funding_status="PENDING"
    ).first()
    batch = _mpo_to_batch(draft_mpo) if draft_mpo else {"supplier": "", "items": []}
    actual = sum(Decimal(str(i.get("total", 0))) for i in batch.get("items", []))
    misc_budget = _misc_planned_budget(active_task)
    variance = misc_budget - actual

    return render(
        request,
        "ad_hoc_purchase_memo.html",
        {
            "active_task": active_task,
            "batch": batch,
            "actual": actual,
            "budget_x": misc_budget,
            "misc_budget": misc_budget,
            "variance": variance,
            "variance_over": variance < 0,
        },
    )
    
# =================================================
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from .models import ProjectTask

@login_required
def print_fluid_ro_view(request):
    """
    Screen or print preview for a draft/submitted ad-hoc RO (before MRO commit).
    """
    context = _fluid_ro_print_context(request)
    if request.GET.get("print") == "1":
        from django.shortcuts import redirect
        from urllib.parse import urlencode

        q = request.GET.copy()
        q.pop("print", None)
        url = reverse("print_fluid_ro_pdf")
        if q:
            url += "?" + urlencode(q, doseq=True)
        return redirect(url)
    return render(request, "print_mpo.html", context)


def _fluid_ro_print_context(request):
    task_id = request.GET.get("task_id")
    active_task = get_object_or_404(ProjectTask, project_id=task_id)

    mpo_id = request.GET.get("mpo_id")
    if mpo_id:
        draft_mpo = MiscPurchaseOrder.objects.filter(
            id=mpo_id, task=active_task
        ).first()
    else:
        draft_mpo = (
            MiscPurchaseOrder.objects.filter(
                task=active_task,
                funding_status__in=["PENDING", "SUBMITTED"],
            )
            .order_by("-created_at")
            .first()
        )
    batch = _mpo_to_batch(draft_mpo) if draft_mpo else request.session.get(
        "batch_data", {"items": [], "supplier": ""}
    )
    actual = (
        draft_mpo.total_amount
        if draft_mpo and draft_mpo.total_amount
        else sum(Decimal(str(i.get("total", 0))) for i in batch.get("items", []))
    )

    ro_reference = ""
    if draft_mpo:
        ro_reference = (draft_mpo.mpo_number or "").strip()
        if not ro_reference and _mpo_ro_locked(draft_mpo):
            ro_reference = _ensure_mpo_reference(draft_mpo)

    back_url = request.GET.get("return") or (
        reverse("misc_purchase_builder")
        + f"?task_id={active_task.project_id}&ro_list=1"
    )
    context = {
        "mpo": draft_mpo,
        "batch": batch,
        "temp_ro_id": ro_reference or request.session.get("temp_ro_id", ""),
        "ro_reference": ro_reference,
        "actual": actual,
        "active_task": active_task,
        "doc_title": ro_reference or "Ad-Hoc Requisition Order",
        "doc_status": draft_mpo.get_funding_status_display() if draft_mpo else "Draft",
        "auto_print": request.GET.get("print") == "1",
        "back_url": back_url,
    }
    context.update(branding_template_context(request))
    return context


@login_required
def print_fluid_ro_pdf_view(request):
    """Native PDF for draft/submitted ad-hoc RO (mobile pinch-zoom, page thumbnails)."""
    from accounts.misc_doc_pdf import build_pdf_bytes, pdf_inline_response

    context = _fluid_ro_print_context(request)
    mpo = context.get("mpo")
    label = context.get("ro_reference") or "Ad-Hoc-RO"
    try:
        pdf_bytes = build_pdf_bytes("print_mpo.html", context)
    except ImportError:
        messages.error(request, "PDF support is not installed on the server.")
        return redirect(
            reverse("print_fluid_ro") + "?" + request.META.get("QUERY_STRING", "")
        )
    except Exception as exc:
        messages.error(request, f"PDF generation failed: {exc}")
        return redirect(
            reverse("print_fluid_ro") + "?" + request.META.get("QUERY_STRING", "")
        )
    if mpo and mpo.mpo_number:
        label = mpo.mpo_number
    return pdf_inline_response(pdf_bytes, label)


@login_required
def print_mpo_view(request, mpo_id):
    """Printable ad-hoc RO from a persisted MPO record."""
    context = _mpo_print_context(request, mpo_id)
    if request.GET.get("print") == "1":
        from django.shortcuts import redirect
        from urllib.parse import urlencode

        q = request.GET.copy()
        q.pop("print", None)
        url = reverse("print_mpo_pdf", kwargs={"mpo_id": mpo_id})
        if q:
            url += "?" + urlencode(q, doseq=True)
        return redirect(url)
    return render(request, "print_mpo.html", context)


def _mpo_print_context(request, mpo_id):
    mpo = get_object_or_404(MiscPurchaseOrder, id=mpo_id)
    batch = _mpo_to_batch(mpo)
    back_url = request.GET.get("return") or (
        reverse("misc_purchase_builder")
        + f"?task_id={mpo.task.project_id}&ro_list=1"
    )
    context = {
        "mpo": mpo,
        "batch": batch,
        "active_task": mpo.task,
        "actual": mpo.total_amount,
        "ro_reference": mpo.mpo_number or "",
        "doc_title": mpo.mpo_number or "Ad-Hoc Requisition Order",
        "doc_status": mpo.get_funding_status_display(),
        "auto_print": request.GET.get("print") == "1",
        "back_url": back_url,
    }
    context.update(branding_template_context(request))
    return context


@login_required
def print_mpo_pdf_view(request, mpo_id):
    """Native PDF for persisted ad-hoc RO / MPO."""
    from accounts.misc_doc_pdf import build_pdf_bytes, pdf_inline_response

    context = _mpo_print_context(request, mpo_id)
    mpo = context["mpo"]
    try:
        pdf_bytes = build_pdf_bytes("print_mpo.html", context)
    except ImportError:
        messages.error(request, "PDF support is not installed on the server.")
        return redirect(reverse("print_mpo", kwargs={"mpo_id": mpo_id}))
    except Exception as exc:
        messages.error(request, f"PDF generation failed: {exc}")
        return redirect(reverse("print_mpo", kwargs={"mpo_id": mpo_id}))
    return pdf_inline_response(pdf_bytes, mpo.mpo_number or f"RO-{mpo.id}")


@login_required
def print_mro_view(request, mro_id):
    """Screen HTML preview for a committed Misc Requisition Order (MRO)."""
    context = _mro_print_context(request, mro_id)
    if request.GET.get("print") == "1":
        from django.shortcuts import redirect
        from urllib.parse import urlencode

        q = request.GET.copy()
        q.pop("print", None)
        url = reverse("print_mro_pdf", kwargs={"mro_id": mro_id})
        if q:
            url += "?" + urlencode(q, doseq=True)
        return redirect(url)
    return render(request, "print_mro.html", context)


def _mro_print_context(request, mro_id):
    mro = get_object_or_404(
        MiscRequisitionOrder.objects.select_related(
            "task", "source_mpo", "authorized_by"
        ),
        pk=mro_id,
    )
    mpo = mro.source_mpo
    items = list(mpo.items.all().order_by("id")) if mpo else []
    budget = _task_budget_record(mro.task)
    back_url = request.GET.get("return") or (
        reverse("misc_purchase_builder")
        + f"?task_id={mro.task.project_id}&ro_list=1"
    )
    context = {
        "mro": mro,
        "mpo": mpo,
        "active_task": mro.task,
        "items": items,
        "budget": budget,
        "auto_print": request.GET.get("print") == "1",
        "back_url": back_url,
    }
    context.update(branding_template_context(request))
    return context


@login_required
def print_mro_pdf_view(request, mro_id):
    """Native PDF for committed MRO (mobile pinch-zoom, page thumbnails)."""
    from accounts.misc_doc_pdf import build_pdf_bytes, pdf_inline_response

    context = _mro_print_context(request, mro_id)
    mro = context["mro"]
    try:
        pdf_bytes = build_pdf_bytes("print_mro.html", context)
    except ImportError:
        messages.error(request, "PDF support is not installed on the server.")
        return redirect(reverse("print_mro", kwargs={"mro_id": mro_id}))
    except Exception as exc:
        messages.error(request, f"PDF generation failed: {exc}")
        return redirect(reverse("print_mro", kwargs={"mro_id": mro_id}))
    return pdf_inline_response(pdf_bytes, mro.mro_number or f"MRO-{mro.id}")
# ========================================================================== Budget
from django.shortcuts import render
from django.db.models import Sum
from decimal import Decimal

from .models import ProjectBudget, PaymentOrder, LPOTransaction, TaskDisbursementPayment


def _task_lpo_paid_total(task):
    """Sum LPO totals that have at least one director-confirmed payment."""
    if not task:
        return Decimal("0.00")
    paid_lpo_ids = PaymentOrder.objects.filter(
        grn__lpo__project_task=task,
        is_confirmed_by_director=True,
    ).values_list("grn__lpo_id", flat=True).distinct()
    return (
        LPOTransaction.objects.filter(id__in=paid_lpo_ids).aggregate(
            t=Sum("total_amount")
        )["t"]
        or Decimal("0.00")
    )


def _task_budget_actual_spend(task):
    """Actual spend for a task using current schema (no selected_quote)."""
    if not task:
        return Decimal("0.00")
    gm = (
        TaskDisbursementPayment.objects.filter(task=task).aggregate(t=Sum("amount"))[
            "t"
        ]
        or Decimal("0.00")
    )
    lpo = _task_lpo_paid_total(task)
    misc = _misc_locked_total(task)
    if gm > 0:
        return gm + lpo
    return lpo + misc


@login_required
def budget_overview(request):
    budgets = ProjectBudget.objects.select_related("task").all()

    rows = []
    grand_budget = Decimal("0.00")
    grand_actual = Decimal("0.00")

    for b in budgets:
        budget_value = b.total_authorized_budget or Decimal("0.00")
        actual_value = _task_budget_actual_spend(b.task)
        variance = budget_value - actual_value
        grand_budget += budget_value
        grand_actual += actual_value

        rows.append({
            "task_id": b.task.project_id if b.task else "N/A",
            "budget_label": b.budget_label,
            "budget_type": b.get_budget_type_display() if b.budget_type else "—",
            "budget": float(budget_value),
            "actual": float(actual_value),
            "variance": float(variance),
            "over": variance < 0,
        })

    return render(
        request,
        "budget_overview.html",
        {
            "rows": rows,
            "grand_budget": float(grand_budget),
            "grand_actual": float(grand_actual),
            "grand_variance": float(grand_budget - grand_actual),
        },
    )
   
# ============================================================================

@login_required
def misc_budget_actuals_view(request):
    """Ad-hoc purchase audit: Misc budget vs locked actuals and variance."""
    tasks = ProjectTask.objects.all().order_by("project_id")
    active_task = _task_from_request(request, tasks)
    if not active_task:
        if not tasks.exists():
            messages.error(request, "No project task found.")
            return redirect("dashboard")
        return render(request, "misc_budget_actuals.html", {
            "tasks": tasks,
            "active_task": None,
            "no_task_selected": True,
            "locked_audit_trail": [],
            "locked_mpos": [],
            "officer_vouchers": [],
            "misc_budget": Decimal("0.00"),
            "misc_actuals": Decimal("0.00"),
            "variance": Decimal("0.00"),
            "variance_over": False,
        })

    locked_mros = MiscRequisitionOrder.objects.filter(
        task=active_task,
        funding_status__in=["LOCKED", "DISBURSED", "RECONCILED"],
    ).order_by("-updated_at")
    locked_mpos = MiscPurchaseOrder.objects.filter(
        task=active_task,
        funding_status__in=["LOCKED", "DISBURSED"],
    ).order_by("-created_at")
    officer_vouchers = (
        AdHocOfficerPaymentVoucher.objects.filter(task=active_task)
        .select_related("mpo")
        .prefetch_related("lines__mpo_item")
        .order_by("-created_at")
    )
    officer_paid_total = (
        officer_vouchers.aggregate(t=Sum("amount"))["t"] or Decimal("0.00")
    )

    misc_budget = _misc_planned_budget(active_task)
    misc_actuals = _misc_locked_total(active_task)
    variance = misc_budget - misc_actuals
    task_has_baseline = _task_has_adhoc_baseline(active_task)
    baseline_mro = _get_task_baseline_mro(active_task)
    mro_registry = _misc_task_mro_registry(active_task)

    return render(
        request,
        "misc_budget_actuals.html",
        {
            "tasks": tasks,
            "active_task": active_task,
            "locked_audit_trail": locked_mros,
            "locked_mpos": locked_mpos,
            "officer_vouchers": officer_vouchers,
            "officer_paid_total": officer_paid_total,
            "misc_budget": misc_budget,
            "misc_actuals": misc_actuals,
            "variance": variance,
            "variance_over": variance < 0,
            "task_has_baseline": task_has_baseline,
            "baseline_mro": baseline_mro,
            "baseline_mro_ref": baseline_mro.mro_number if baseline_mro else "",
            "mro_registry": mro_registry,
        },
    )


def _prune_duplicate_adhoc_mros(task):
    """
    Remove duplicate MRO ledger rows left by double budget commits (dev cleanup).
    Keeps the MRO linked to its MPO; drops orphan duplicates and their budget lines.
    """
    removed = []
    linked = list(
        MiscRequisitionOrder.objects.filter(task=task, source_mpo_id__isnull=False)
    )
    linked_mpo_ids = {m.source_mpo_id for m in linked}
    orphans = MiscRequisitionOrder.objects.filter(
        task=task, source_mpo_id__isnull=True
    ).order_by("created_at")
    if linked_mpo_ids:
        for mro in orphans:
            label = mro.mro_number or str(mro.id)[:8]
            if mro.mro_number:
                BudgetTransaction.objects.filter(
                    category="MISC",
                    description__icontains=mro.mro_number,
                ).delete()
            mro.delete()
            removed.append(label)
        return removed
    orphan_list = list(orphans)
    if len(orphan_list) <= 1:
        return removed
    keep = orphan_list[-1]
    for mro in orphan_list[:-1]:
        label = mro.mro_number or str(mro.id)[:8]
        if mro.mro_number:
            BudgetTransaction.objects.filter(
                category="MISC",
                description__icontains=mro.mro_number,
            ).delete()
        mro.delete()
        removed.append(label)
    return removed


@login_required
def authorize_mpo_action(request):
    if request.method != "POST":
        return redirect("misc_purchase_builder")

    task_id = request.POST.get("task_id") or request.session.get("active_task_id")
    active_task = get_object_or_404(ProjectTask, project_id=task_id)
    mpo_id = request.POST.get("mpo_id")

    misc_ok, misc_reason = _misc_channel_allowed(active_task)
    if not misc_ok:
        messages.error(request, misc_reason)
        return redirect(f"/misc-purchase/?task_id={active_task.project_id}")

    try:
        with transaction.atomic():
            if mpo_id:
                draft_mpo = (
                    MiscPurchaseOrder.objects.select_for_update()
                    .filter(id=mpo_id, task=active_task)
                    .first()
                )
            else:
                draft_mpo = (
                    MiscPurchaseOrder.objects.select_for_update()
                    .filter(task=active_task, funding_status="SUBMITTED")
                    .order_by("-created_at")
                    .first()
                )

            if not draft_mpo or not draft_mpo.items.exists():
                messages.error(
                    request,
                    "Submit an RO with at least one line item before authorization.",
                )
                return redirect(f"/misc-purchase/?task_id={active_task.project_id}")

            existing_mro = MiscRequisitionOrder.objects.filter(
                source_mpo=draft_mpo
            ).first()
            if (
                MiscRequisitionOrder.objects.filter(task=active_task)
                .exclude(source_mpo=draft_mpo)
                .exists()
            ):
                messages.error(
                    request,
                    "This task already has its MRO baseline. One budget and one MRO per task.",
                )
                return redirect(f"/misc-purchase/?task_id={active_task.project_id}")
            if existing_mro or draft_mpo.funding_status in ("LOCKED", "DISBURSED"):
                mro = existing_mro or getattr(draft_mpo, "committed_mro", None)
                mro_ref = mro.mro_number if mro else "committed"
                messages.info(
                    request,
                    f"Already committed — {draft_mpo.mpo_number} / {mro_ref}. No duplicate was created.",
                )
                return redirect(
                    f"/misc-purchase/?task_id={active_task.project_id}"
                )

            if draft_mpo.funding_status not in ("SUBMITTED", "PENDING"):
                messages.error(request, "This RO cannot be committed in its current state.")
                return redirect(f"/misc-purchase/?task_id={active_task.project_id}")

            if draft_mpo.funding_status == "PENDING" and draft_mpo.is_sourcing:
                messages.error(
                    request,
                    "Lock and submit the RO before committing the ad-hoc budget.",
                )
                return redirect(f"/misc-purchase/?task_id={active_task.project_id}")

            total = _recalc_mpo_total(draft_mpo)
            _ensure_mpo_reference(draft_mpo)
            ro_total = _money(request.POST, "RO-total_amount", str(total))
            if request.POST.get("budget-material_total_cost"):
                _save_task_budget(
                    active_task,
                    ProjectBudget.BUDGET_ADHOC_MISC,
                    _money(request.POST, "budget-material_total_cost", str(total)),
                    _money(request.POST, "budget-labour_burden"),
                    _money(request.POST, "budget-misc_reserve"),
                    _money(
                        request.POST,
                        "budget-total_authorized_budget",
                        request.POST.get("grand_total", str(total)),
                    ),
                    label=f"Ad-Hoc Budget — {active_task.project_id}",
                )
            budget = _task_budget_record(active_task)

            draft_mpo.funding_status = "LOCKED"
            draft_mpo.is_sourcing = False
            draft_mpo.total_amount = ro_total
            draft_mpo.save(
                update_fields=["funding_status", "is_sourcing", "total_amount"]
            )

            mro = MiscRequisitionOrder.objects.create(
                task=active_task,
                source_mpo=draft_mpo,
                mro_number=_next_mro_number(),
                funding_status="LOCKED",
                total_amount=ro_total,
                messenger_name=draft_mpo.messenger_name,
                is_sourcing=False,
                authorized_by=request.user,
            )

            if not budget:
                budget = _save_task_budget(
                    active_task,
                    ProjectBudget.BUDGET_ADHOC_MISC,
                    ro_total,
                    Decimal("0.00"),
                    Decimal("0.00"),
                    ro_total,
                    label=f"Ad-Hoc Budget — {active_task.project_id}",
                )

            BudgetTransaction.objects.create(
                budget=budget,
                category="MISC",
                amount=ro_total,
                description=f"Ad-hoc RO {draft_mpo.mpo_number} / {mro.mro_number}",
            )

        _prune_duplicate_adhoc_mros(active_task)
        request.session["batch_data"] = {"items": [], "supplier": ""}
        request.session["temp_ro_id"] = None
        request.session.modified = True
        messages.success(
            request,
            f"Locked {draft_mpo.mpo_number} / {mro.mro_number} — {fmt_money(total)} posted to audit.",
        )
        return redirect(
            f"/misc-purchase/?task_id={active_task.project_id}"
        )
    except Exception as e:
        messages.error(request, f"Authorization failed: {e}")
        return redirect(f"/misc-purchase/?task_id={active_task.project_id}")
    
# ================================================================
from django.db import transaction

def sync_procurement_chain(task, item_data, supplier, lpo_no):
    """
    Orchestrates the chain: 
    1. Ensures BOM/RO exists.
    2. Appends RFQ entry.
    3. Finalizes LPO.
    """
    with transaction.atomic():
        # 1. RO & BOM are your base - verify they exist
        ro, _ = RequisitionOrder.objects.get_or_create(task=task)
        
        # 2. RFQ: Append or Update the pricing record
        rfq, created = RFQTransaction.objects.update_or_create(
            bom_item_id=item_data['id'],
            supplier=supplier,
            defaults={'unit_cost_quoted': item_data['price']}
        )
        
        # 3. LPO: The final destination
        lpo = LPOTransaction.objects.create(
            lpo_no=lpo_no,
            supplier=supplier,
            project_task=task,
            variance_explanation="System-triggered chain update",
        )
        return lpo


# ==============================================================

from django.shortcuts import redirect
from django.utils import timezone
from django.db import transaction
from django.shortcuts import redirect, get_object_or_404
from django.db import transaction
from django.utils import timezone

@login_required
def commit_lpo(request, task_id):

    task = get_object_or_404(ProjectTask, project_id=task_id)

    if request.method != "POST":
        return redirect("bid_evaluation_terminal_view")

    lpo = LPOTransaction.objects.create(
        lpo_no=f"LPO-{task.project_id}-{timezone.now().strftime('%Y%m%d%H%M%S')}",
        project_task=task,
        status="LOCKED"
    )

    return redirect("print_lpo_view", lpo_id=lpo.id)


# ==============================================================================
# GM AIE — Accounting, Operations & Maintenance Disbursement
# ==============================================================================

DISBURSEMENT_BUDGET_LINES = [
    (TaskDisbursementPayment.LINE_MATERIAL, "material_total_cost", "Payment of Goods"),
    (TaskDisbursementPayment.LINE_MAINTENANCE, "misc_reserve", "Office Maintenance & Ops"),
    (TaskDisbursementPayment.LINE_LABOUR, "labour_burden", "Labour"),
    (TaskDisbursementPayment.LINE_EQUIPMENT, "equipment_reserve", "Equipment Hire / Purchase"),
]


def _next_disbursement_payment_number():
    year = timezone.now().year
    prefix = f"PAY-{year}-"
    last = (
        TaskDisbursementPayment.objects.filter(payment_number__startswith=prefix)
        .order_by("-payment_number")
        .first()
    )
    seq = int(last.payment_number.split("-")[-1]) + 1 if last and last.payment_number else 1
    return f"{prefix}{seq:04d}"


def _task_project_class(task):
    """Major vs Ad-Hoc label derived from committed budget channel."""
    budget = _task_budget_record(task)
    if budget and budget.budget_type == ProjectBudget.BUDGET_ADHOC_MISC:
        return {"label": "Project (Ad-Hoc)", "css": "task-adhoc", "code": "ADHOC"}
    if budget and budget.budget_type == ProjectBudget.BUDGET_RFQ_LPO:
        return {"label": "Project (Major)", "css": "task-major", "code": "MAJOR"}
    if MiscPurchaseOrder.objects.filter(task=task).exists():
        return {"label": "Project (Ad-Hoc)", "css": "task-adhoc", "code": "ADHOC"}
    if LPOTransaction.objects.filter(project_task=task).exists():
        return {"label": "Project (Major)", "css": "task-major", "code": "MAJOR"}
    return {"label": "Task (Uncommitted)", "css": "task-neutral", "code": "NONE"}


def _disbursement_line_budget_amount(budget, line_key):
    field_map = {k: f for k, f, _ in DISBURSEMENT_BUDGET_LINES}
    if not budget:
        return Decimal("0.00")
    return getattr(budget, field_map[line_key], Decimal("0.00")) or Decimal("0.00")


def _disbursement_line_actual(task, line_key):
    return (
        TaskDisbursementPayment.objects.filter(task=task, budget_line=line_key).aggregate(
            t=Sum("amount")
        )["t"]
        or Decimal("0.00")
    )


def _task_disbursement_budget_summary(task):
    budget = _task_budget_record(task)
    lines = []
    for key, _field, label in DISBURSEMENT_BUDGET_LINES:
        bud = _disbursement_line_budget_amount(budget, key)
        actual = _disbursement_line_actual(task, key)
        variance = bud - actual
        lines.append({
            "key": key,
            "label": label,
            "budget": bud,
            "actual": actual,
            "bfwd": actual,
            "variance": variance,
            "over": variance < 0,
        })
    total_budget = sum(l["budget"] for l in lines)
    total_actual = sum(l["actual"] for l in lines)
    return {
        "lines": lines,
        "total_budget": total_budget,
        "total_actual": total_actual,
        "total_variance": total_budget - total_actual,
        "has_budget": budget is not None,
        "budget_label": budget.budget_label if budget else "",
        "budget_version": budget.version if budget else 0,
        "is_ceo_approved": bool(budget and budget.is_ceo_approved),
        "fund_released": CEOFundRelease.objects.filter(task=task).exists(),
    }


def _disbursement_payment_listing(task, active_payment=None):
    rows = []
    active_id = str(active_payment.id) if active_payment else None
    for p in TaskDisbursementPayment.objects.filter(task=task).order_by("-created_at"):
        rows.append({
            "id": str(p.id),
            "ref": p.payment_number,
            "line": p.get_budget_line_display(),
            "line_key": p.budget_line,
            "amount": p.amount,
            "description": p.description,
            "date": p.created_at,
            "is_active": active_id == str(p.id),
        })
    return rows


def _gm_resolve_active_task(request, tasks):
    return _task_from_request(request, tasks)


def _gm_task_sidebar_capabilities(task, project_class, budget_summary):
    code = project_class["code"]
    is_major = code == "MAJOR"
    is_adhoc = code == "ADHOC"
    has_budget = budget_summary.get("has_budget", False)
    approved = budget_summary.get("is_ceo_approved", False)
    released = budget_summary.get("fund_released", False)

    if is_major:
        grn_hint = "LPO → GRN → supplier payment voucher on this task."
        adhoc_hint = "Officer RO advances — not active on this task yet."
        workflow = "Major — LPO · GRN · Supplier payment voucher"
    elif is_adhoc:
        grn_hint = "LPO · GRN · supplier PV — not active on this task yet."
        adhoc_hint = "RO item @ price → payment voucher (cash/M-Pesa), partial or full per line."
        workflow = "Ad-Hoc — RO · Officer payment voucher"
    else:
        grn_hint = "Opens when this task has a Major budget channel or LPO/GRN activity."
        adhoc_hint = "Opens when this task has an Ad-Hoc budget channel or RO activity."
        workflow = "Uncommitted — no procurement lane until budget or activity is set"

    budget_hint = ""
    if not has_budget:
        budget_hint = "No provision budget on this task."
    elif not approved:
        budget_hint = "Budget not CEO-approved yet."
    elif not released:
        budget_hint = "CEO funds not released to GM yet."

    return {
        "is_major": is_major,
        "is_adhoc": is_adhoc,
        "is_uncommitted": code == "NONE",
        "has_budget": has_budget,
        "budget_approved": approved,
        "fund_released": released,
        "enable_grn": is_major,
        "enable_supplier_pv": is_major,
        "enable_goods_status": is_major,
        "enable_adhoc_ro": is_adhoc,
        "enable_officer_pv": is_adhoc,
        "grn_hint": grn_hint,
        "supplier_pv_hint": grn_hint,
        "adhoc_ro_hint": adhoc_hint,
        "officer_pv_hint": adhoc_hint,
        "budget_hint": budget_hint,
        "workflow_label": workflow,
    }


@login_required
def gm_aie_disbursement_view(request):
    """GM Accounting office — AIE disbursement against four budget lines per task."""
    tasks = ProjectTask.objects.all().order_by("project_id")
    active_task = _gm_resolve_active_task(request, tasks)
    if not active_task:
        return render(request, "gm_aie_disbursement.html", {
            "tasks": tasks,
            "no_tasks": not tasks.exists(),
            "no_task_selected": tasks.exists(),
            "active_task": None,
        })

    project_class = _task_project_class(active_task)
    budget_summary = _task_disbursement_budget_summary(active_task)
    task_caps = _gm_task_sidebar_capabilities(active_task, project_class, budget_summary)

    if request.method == "POST":
        if request.POST.get("action") == "create_payment_voucher":
            return _gm_create_payment_voucher(request, active_task, task_caps)
        if request.POST.get("action") == "create_officer_payment_voucher":
            return _gm_create_officer_payment_voucher(request, active_task, task_caps)
        if request.POST.get("action") == "settle_officer_payment_voucher":
            return _gm_settle_officer_payment_voucher(request, active_task, task_caps)
        try:
            with transaction.atomic():
                if "post_payment" in request.POST:
                    budget = _task_budget_record(active_task)
                    if not budget:
                        raise ValueError(
                            "No CEO-authorized budget for this task. Complete budget approval first."
                        )
                    if not budget.is_ceo_approved:
                        raise ValueError(
                            "Budget not CEO-approved. Approve budget before GM disbursements."
                        )
                    if not CEOFundRelease.objects.filter(task=active_task).exists():
                        raise ValueError(
                            "CEO has not released funds to GM Accounting for this task yet."
                        )
                    line = request.POST.get("budget_line", "").strip()
                    valid_lines = {k for k, _, _ in DISBURSEMENT_BUDGET_LINES}
                    if line not in valid_lines:
                        raise ValueError("Select a valid budget line category.")
                    amount = Decimal(str(request.POST.get("amount", 0) or 0))
                    if amount <= 0:
                        raise ValueError("Payment amount must be greater than zero.")
                    description = (request.POST.get("description") or "").strip()
                    if not description:
                        raise ValueError("Enter a payment description.")
                    payee = (request.POST.get("payee") or "").strip()
                    method = request.POST.get("payment_method", "BANK")
                    aie_ref = (request.POST.get("aie_reference") or "").strip()
                    payment = TaskDisbursementPayment.objects.create(
                        payment_number=_next_disbursement_payment_number(),
                        task=active_task,
                        budget_line=line,
                        description=description,
                        payee=payee,
                        amount=amount,
                        payment_method=method,
                        aie_reference=aie_ref,
                        posted_by=request.user,
                    )
                    messages.success(
                        request,
                        f"Payment {payment.payment_number} posted — US$ {amount:.2f} ({payment.get_budget_line_display()}).",
                    )
                    return redirect(
                        f"/gm-disbursement/?task_id={active_task.project_id}"
                        f"&payment_id={payment.id}&pay_list=1"
                    )
        except Exception as e:
            messages.error(request, f"Payment failed: {e}")
        return redirect(f"/gm-disbursement/?task_id={active_task.project_id}")

    view_payment_id = request.GET.get("payment_id")
    viewed_payment = None
    if view_payment_id:
        viewed_payment = TaskDisbursementPayment.objects.filter(
            id=view_payment_id, task=active_task
        ).first()

    budget_summary = _task_disbursement_budget_summary(active_task)
    payment_listing = _disbursement_payment_listing(active_task, viewed_payment)
    pay_mode = "detail" if viewed_payment else "entry"

    period_start, period_end, period_from, period_to = _parse_month_period(
        request.GET.get("period_from", ""),
        request.GET.get("period_to", ""),
    )
    grn_period_listing = _serialize_task_grns(active_task, period_start, period_end)
    voucher_period_listing = _serialize_task_payment_vouchers(
        active_task, period_start, period_end
    )
    grns_data = _serialize_task_grns(active_task)
    banks_data = _banks_select_data()
    adhoc_ros_data = _serialize_task_adhoc_ros_for_purchase(active_task)
    lpo_goods_status_data = _serialize_lpo_goods_status(active_task)
    officer_voucher_period_listing = _serialize_task_officer_vouchers(
        active_task, period_start, period_end
    )

    return render(
        request,
        "gm_aie_disbursement.html",
        {
            "tasks": tasks,
            "active_task": active_task,
            "project_class": project_class,
            "task_caps": task_caps,
            "budget_summary": budget_summary,
            "payment_listing": payment_listing,
            "viewed_payment": viewed_payment,
            "pay_mode": pay_mode,
            "pay_list_open": request.GET.get("pay_list") == "1",
            "budget_lines": DISBURSEMENT_BUDGET_LINES,
            "pay_methods": TaskDisbursementPayment.PAY_METHODS,
            "budget_locked": budget_summary.get("is_ceo_approved"),
            "fund_released": budget_summary.get("fund_released"),
            "period_from": period_from,
            "period_to": period_to,
            "grn_period_listing": grn_period_listing,
            "voucher_period_listing": voucher_period_listing,
            "grns_data": grns_data,
            "banks_data": banks_data,
            "adhoc_ros_data": adhoc_ros_data,
            "lpo_goods_status_data": lpo_goods_status_data,
            "officer_voucher_period_listing": officer_voucher_period_listing,
            "grn_period_open": request.GET.get("open_grn_period") == "1",
            "voucher_period_open": request.GET.get("open_voucher_period") == "1",
            "adhoc_ro_period_open": request.GET.get("open_adhoc_ro_period") == "1",
            "officer_pv_period_open": request.GET.get("open_officer_pv_period") == "1",
            "goods_status_open": request.GET.get("open_goods_status") == "1",
        },
    )


# ==============================================================================
# CEO — Budget Authorization & Funds Disbursement to GM
# ==============================================================================

def _next_fund_release_number():
    """
    Global CEO→GM fund disbursement voucher (PV-DSB series only).
    Not shared with procurement PaymentOrder (PV-YYYY-*) or GM desk payments (PAY-*).
    One sequence across all major and ad-hoc project budgets.
    """
    year = timezone.now().year
    prefix = f"PV-DSB-{year}-"
    last = (
        CEOFundRelease.objects.filter(release_number__startswith=prefix)
        .order_by("-release_number")
        .first()
    )
    seq = int(last.release_number.split("-")[-1]) + 1 if last and last.release_number else 1
    return f"{prefix}{seq:04d}"


def _task_budget_provision_lines(task):
    """Authorized budget lines only (no actuals) for CEO fund-transfer voucher."""
    budget = _task_budget_record(task)
    lines = []
    for _key, _field, label in DISBURSEMENT_BUDGET_LINES:
        amount = _disbursement_line_budget_amount(budget, _key)
        lines.append({"label": label, "budget": amount})
    total = sum((ln["budget"] for ln in lines), Decimal("0.00"))
    return {
        "lines": lines,
        "total_budget": total,
        "budget_label": budget.budget_label if budget else "",
        "budget_version": budget.version if budget else 0,
        "ceo_aie_reference": budget.ceo_aie_reference if budget else "",
    }


def _build_ceo_fund_release_voucher_context(release):
    task = release.task
    budget = release.budget
    provision = _task_budget_provision_lines(task)
    ceo_name = ""
    if release.authorized_by:
        ceo_name = release.authorized_by.get_full_name() or release.authorized_by.get_username()
    elif budget and budget.approved_by:
        u = budget.approved_by
        ceo_name = u.get_full_name() or u.get_username()
    return {
        "release": release,
        "pv_no": release.release_number,
        "task": task,
        "budget": budget,
        "provision_lines": provision["lines"],
        "total_budget": provision["total_budget"],
        "budget_label": provision["budget_label"],
        "budget_version": provision["budget_version"],
        "ceo_aie_reference": release.aie_memo_ref or provision["ceo_aie_reference"],
        "ceo_name": ceo_name,
        "back_url": f"/budget-approval/?task_id={task.project_id}",
    }


@login_required
def print_ceo_fund_release_voucher_view(request, release_id):
    """Print CEO fund-transfer payment voucher + cover memo to GM (budget lines, no actuals)."""
    release = get_object_or_404(
        CEOFundRelease.objects.select_related(
            "task", "budget", "authorized_by", "budget__approved_by"
        ),
        id=release_id,
    )
    context = _build_ceo_fund_release_voucher_context(release)
    context["auto_print"] = request.GET.get("print") == "1"
    return render(request, "ceo_fund_release_voucher_print.html", context)


@login_required
def budget_approval_view(request):
    """CEO AIE: approve provision budget (lock lines) then release funds to GM Accounting."""
    tasks = ProjectTask.objects.all().order_by("project_id")
    if not tasks.exists():
        return render(request, "budget_approval.html", {"tasks": [], "no_tasks": True})
    active_task = _task_from_request(request, tasks, include_post=(request.method == "POST"))
    if not active_task:
        return render(request, "budget_approval.html", {
            "tasks": tasks,
            "no_tasks": False,
            "no_task_selected": True,
            "active_task": None,
        })

    budget = _task_budget_record(active_task)
    project_class = _task_project_class(active_task)
    budget_summary = _task_disbursement_budget_summary(active_task)
    fund_release = CEOFundRelease.objects.filter(task=active_task).order_by("-released_at").first()

    if request.method == "POST":
        try:
            with transaction.atomic():
                budget = _task_budget_record(active_task)
                if "approve_budget" in request.POST:
                    if not budget:
                        raise ValueError(
                            "No provision budget for this task. "
                            "Complete Bid Evaluation (Major) or Ad-Hoc Purchase first."
                        )
                    if budget.total_authorized_budget <= 0:
                        raise ValueError("Provision budget total must be greater than zero.")
                    if budget.is_ceo_approved:
                        raise ValueError("Budget is already CEO-approved and locked.")
                    aie_ref = (request.POST.get("ceo_aie_reference") or "").strip()
                    budget.is_ceo_approved = True
                    budget.approved_at = timezone.now()
                    budget.approved_by = request.user
                    budget.ceo_aie_reference = aie_ref
                    budget.save(
                        update_fields=[
                            "is_ceo_approved",
                            "approved_at",
                            "approved_by",
                            "ceo_aie_reference",
                        ]
                    )
                    messages.success(
                        request,
                        f"Budget locked for Task {active_task.project_id} — "
                        f"US$ {budget.total_authorized_budget:.2f} CEO AIE approved.",
                    )

                elif "release_funds" in request.POST:
                    if not budget or not budget.is_ceo_approved:
                        raise ValueError("Approve and lock the budget before releasing funds.")
                    if CEOFundRelease.objects.filter(task=active_task).exists():
                        raise ValueError("Funds already released to GM Accounting for this task.")
                    bank_ref = (request.POST.get("bank_reference") or "").strip()
                    if not bank_ref:
                        raise ValueError("Enter the bank transfer reference.")
                    memo = (request.POST.get("aie_memo_ref") or budget.ceo_aie_reference or "").strip()
                    CEOFundRelease.objects.create(
                        release_number=_next_fund_release_number(),
                        task=active_task,
                        budget=budget,
                        amount=budget.total_authorized_budget,
                        transfer_method="BANK",
                        from_office=(request.POST.get("from_office") or "").strip()
                        or "CEO Office — Authority to Incur Expenditure (AIE)",
                        to_officer=(request.POST.get("to_officer") or "").strip()
                        or "GM — Accounting Officer",
                        bank_reference=bank_ref,
                        aie_memo_ref=memo,
                        notes=(request.POST.get("release_notes") or "").strip(),
                        authorized_by=request.user,
                    )
                    messages.success(
                        request,
                        f"Bank transfer US$ {budget.total_authorized_budget:.2f} "
                        f"authorized to GM Accounting Officer.",
                    )
        except Exception as e:
            messages.error(request, str(e))
        return redirect(f"/budget-approval/?task_id={active_task.project_id}")

    provision_status = "none"
    if budget:
        provision_status = "locked" if budget.is_ceo_approved else "provision"

    return render(
        request,
        "budget_approval.html",
        {
            "tasks": tasks,
            "active_task": active_task,
            "project_class": project_class,
            "budget": budget,
            "budget_summary": budget_summary,
            "provision_status": provision_status,
            "fund_release": fund_release,
            "can_approve": bool(budget and not budget.is_ceo_approved),
            "can_release": bool(
                budget and budget.is_ceo_approved and not fund_release
            ),
            "can_gm_pay": bool(
                budget and budget.is_ceo_approved and fund_release
            ),
        },
    )