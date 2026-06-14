import re
import json
from decimal import Decimal
from django.utils import timezone
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.contrib.auth.models import User
from django.http import JsonResponse, HttpResponseForbidden
from django.views.decorators.csrf import csrf_exempt
from django.forms.models import model_to_dict
from django.db.models import Sum, F, Count

# SINGLE UNIFIED IMPORT BLOCK - All models imported exactly once
from .models import (
    UserAccount, UserCategory, BankAccount, SupplierAccount, 
    GLAccount, GLAnalysisCategory, ProjectTask, ProjectBuildCategory, 
    Product, ProjectBuilding, BOMHeader, BOMItem, 
    RequisitionOrder, RequisitionOrderItem, LPOTransaction, 
    RFQTransaction, GRNTransaction, PaymentOrder,MiscRequisitionOrder
)
#=========================================================================

# =======================================================================
# 🔐 AUTH & ACCESS CONTROLLERS
# =======================================================================
class CustomLoginView(LoginView):
    template_name = 'login.html'
    redirect_authenticated_user = True

def has_module_access(user, module_code):
    try:
        return user.useraccount.access_level.modules.filter(code=module_code).exists()
    except:
        return False

# =======================================================================
# 🏠 NAVIGATION CORE
# =======================================================================
def home(request):
    return render(request, 'home.html')

@login_required
def dashboard(request):
    user = request.user
    try:
        user_account = user.useraccount
        role = user_account.access_level.description
        modules = user_account.access_level.modules.all()
    except:
        role = "Project Director"
        modules = []

    context = {
        'username': user.username,
        'role': role,
        'modules': modules,
        'categories': UserCategory.objects.all(),
    }
    return render(request, 'dashboard.html', context)

@login_required
def fin_mgmt_ops_view(request):
    tasks = ProjectTask.objects.all()
    context = {
        'page_title': 'Pioneer Financial Ops',
        'tasks': tasks,
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
        'building': ProjectBuilding,
        'ro': RequisitionOrder,
        'ro_item': RequisitionOrderItem,
        'bom': BOMHeader,
        'bom_item': BOMItem,
        'lpo': LPOTransaction,
        'rfq': RFQTransaction,
    }
    return model_map.get(entity_type.lower())

@login_required
@csrf_exempt
def unified_api_create(request, entity_type):
    """Handles Save/Update for ALL models via AJAX."""
    if request.method == "POST":
        model = get_pioneer_model(entity_type)
        if not model:
            return JsonResponse({'status': 'error', 'message': 'Invalid entity'}, status=400)

        mode = request.POST.get("mode", "create")
        original_id = request.POST.get("original_id")
        
        data = {k: v for k, v in request.POST.items() if k not in ['mode', 'original_id', 'csrfmiddlewaretoken']}
        
        try:
            if mode == "edit" and original_id:
                obj = get_object_or_404(model, pk=original_id)
                for key, value in data.items():
                    setattr(obj, key, value)
                obj.save()
                msg = f"{entity_type.upper()} updated successfully."
            else:
                model.objects.create(**data)
                msg = f"{entity_type.upper()} created successfully."
                
            return JsonResponse({'status': 'success', 'message': msg})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@login_required
def get_entity_list(request, entity_type):
    """Universal Fetcher for the Dashboard tables."""
    model = get_pioneer_model(entity_type)
    if not model:
        return JsonResponse({'status': 'error', 'message': 'Invalid entity'}, status=400)
    
    pk_name = model._meta.pk.name
    queryset = model.objects.all().order_by(f'-{pk_name}').values()
    return JsonResponse({'status': 'success', 'data': list(queryset)})

@login_required
def get_entity_detail(request, entity_type, pk):
    """Pulls 1 record to pre-fill Edit forms."""
    model = get_pioneer_model(entity_type)
    obj = get_object_or_404(model, pk=pk)
    return JsonResponse({'status': 'success', 'data': model_to_dict(obj)})

@login_required
@csrf_exempt
def delete_entity(request, entity_type, pk):
    """Unified endpoint to delete records."""
    model = get_pioneer_model(entity_type)
    if not model:
        return JsonResponse({'status': 'error', 'message': 'Invalid entity'}, status=400)

    try:
        instance = get_object_or_404(model, pk=pk)
        instance.delete()
        return JsonResponse({'status': 'success', 'message': f'Record {pk} deleted.'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@login_required
def create_user(request):
    if request.method == "POST":
        staff_no = request.POST.get('staff_no')
        first_name = request.POST.get('first_name', '')
        last_name = request.POST.get('last_name', '')
        username = request.POST.get('username')
        email = request.POST.get('email')
        cat_id = request.POST.get('access_level_id')

        try:
            user, created = User.objects.get_or_create(username=username)
            if email:
                user.email = email
            user.save()

            category = UserCategory.objects.filter(id=cat_id).first() if cat_id else None

            UserAccount.objects.update_or_create(
                user=user,
                defaults={
                    'staff_no': staff_no,
                    'first_name': first_name,
                    'last_name': last_name,
                    'designation': request.POST.get('designation'),
                    'phone': request.POST.get('phone'),
                    'email': email,
                    'contact_address': request.POST.get('contact_address', ''),
                    'access_level': category
                }
            )
            return JsonResponse({'status': 'success', 'message': f'User {username} created successfully.'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

    return HttpResponseForbidden("Method not allowed")

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
    task_id = request.GET.get("task_id")
    active_task = ProjectTask.objects.filter(project_id=task_id).first() or tasks.first()

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

@login_required
def bom_builder(request):
    """Unified single logic block called cleanly from urls.py line 41."""
    tasks = ProjectTask.objects.all()
    selected_id = request.GET.get('task_id')
    active_task = ProjectTask.objects.filter(project_id=selected_id).first() or tasks.first()

    bom_header, created = BOMHeader.objects.get_or_create(
        task=active_task,
        defaults={'status': 'DRAFT'}
    )

    if request.method == "POST" and "add_item" in request.POST:
        BOMItem.objects.create(
            header=bom_header,
            pillar_id=2, 
            description=request.POST.get('description'),
            qty=request.POST.get('qty', 0),
            uom=request.POST.get('uom', 'Pcs')
        )
        return redirect(f'/bom-builder/?task_id={active_task.project_id}')

    return render(request, 'bom_builder.html', {
        'tasks': tasks,
        'active_task': active_task,
        'bom_items': bom_header.items.all().order_by('id'),
        'bom_no': bom_header.bom_id,
    })

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
    # 1. Pull core database sets safely using verified model fields
    tasks = ProjectTask.objects.all()
    
    # FIX HERE: Pull all suppliers since 'status' is not an available field
    suppliers = SupplierAccount.objects.all() 
    
    # System Metric Requirement
    total_qualified_suppliers = suppliers.count()
    
    # 2. Extract operational parameters
    task_id = request.GET.get('task_id')
    active_task = None
    build_items = []
    stats = {'sent_count': 0, 'waiting_count': 0}
    # ==========================================================================
    
    if task_id:
        active_task = ProjectTask.objects.filter(project_id=task_id).first()
        
        if active_task:
            # 1. Access the operational Requisition Order document
            ro = RequisitionOrder.objects.filter(task=active_task).first()
            
            if ro:
                # 2. Extract the line items created by the Site Manager's BOM sync script
                build_items = ro.items.all().order_by('id')  # Accesses RequisitionOrderItem rows
                
                # 3. Pull primary keys directly to ensure a clean transaction lookup
                item_ids = build_items.values_list('id', flat=True)
                
                # 4. Target the transactions tied directly to these operational line items
                sent_transactions = RFQTransaction.objects.filter(bom_item_id__in=item_ids)
                
                # 5. Populate dashboard summary statistics metrics
                stats['sent_count'] = sent_transactions.values('supplier_id').distinct().count()
                stats['waiting_count'] = sent_transactions.filter(is_selected=False).values('supplier_id').distinct().count()
            
    #==========================================================================================

    return render(request, 'rfq_manager.html', {
        'tasks': tasks,
        'active_task': active_task,
        'build': build_items,
        'suppliers': suppliers,
        'total_qualified_suppliers': total_qualified_suppliers,
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
                budget, created = ProjectBudget.objects.get_or_create(
                    task=active_task,
                    defaults={
                        "budget_label": f"BUDGET-{active_task.project_id}",
                        "material_total_cost": material_total,
                        "labour_burden": labour_burden,
                        "misc_reserve": misc_reserve,
                        "total_authorized_budget": total_budget,
                    },
                )

                # =================================================
                # UPDATE EXISTING BUDGET
                # =================================================
                if not created:

                    budget.material_total_cost = material_total
                    budget.labour_burden = labour_burden
                    budget.misc_reserve = misc_reserve
                    budget.total_authorized_budget = total_budget

                    budget.version += 1

                    budget.save()

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
import json
from decimal import Decimal
from django.utils import timezone
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from .models import ProjectTask, SupplierAccount

@login_required
def procurement_lpo(request):
    payload = request.POST if request.method == "POST" else request.GET

    if request.method == "POST" and not request.POST.get('supplier_id') and not request.POST.get('project_id'):
        payload = request.GET

    tasks = ProjectTask.objects.all()

    task_id = payload.get('task_id') or payload.get('project_id')
    active_task = ProjectTask.objects.filter(project_id=task_id).first() or tasks.first()

    winner_id = payload.get('winner_id') or payload.get('supplier_id')
    winning_supplier = None
    clean_pk = None

    if winner_id:
        clean_pk = str(winner_id).split(',')[0].strip()
        winning_supplier = SupplierAccount.objects.filter(pk=clean_pk).first()

    vendor_name = winning_supplier.description if winning_supplier else payload.get('supplier') or "Evaluated Contracted Vendor"

    raw_mat_cost = payload.get('mat') or payload.get('material_cost', '0.00')
    materials_total = Decimal(raw_mat_cost or '0.00')

    items_raw = payload.get('items_json', '[]')

    template_items = []
    try:
        parsed_items = json.loads(items_raw)
        for idx, item in enumerate(parsed_items, start=1):
            qty = float(item.get('qty', 0))
            unit_price = float(item.get('unit_price', item.get('price', 0)))
            line_total = float(item.get('line_total', qty * unit_price))

            template_items.append({
                'id': item.get('id', str(idx)),
                'desc': item.get('desc', 'Material Line Item'),
                'qty': qty,
                'uom': item.get('uom', 'PCS'),
                'price': unit_price,
                'total': line_total,
            })
    except:
        template_items = []


    # ============================================================
    # 🧠 NEW: LPO COMMIT LAYER (PERSISTENCE PATCH)
    # ============================================================
    lpo_saved = None

    if request.method == "POST" and payload.get("commit_lpo") == "true":
        from .models import LPOTransaction, RFQTransaction

        rfq_id = payload.get("rfq_id")
        rfq = RFQTransaction.objects.filter(pk=rfq_id).first()

        if active_task and rfq:

            lpo_saved = LPOTransaction.objects.create(
                lpo_no=f"LPO-{active_task.project_id}-{timezone.now().strftime('%m%d%Y%H%M')}",
                selected_quote=rfq,
                project_task=active_task,
                building_id=payload.get("building_id"),
                build_category_id=payload.get("build_category_id"),
                variance_explanation=payload.get("variance_explanation", ""),
                stars=int(payload.get("stars", 0))
            )

    # ============================================================

    context = {
        'tasks': tasks,
        'task': active_task,
        'supplier_account': winning_supplier,
        'winning_supplier': vendor_name,
        'items': template_items,
        'materials_total': materials_total,
        'lpo_no': f"LPO-{active_task.project_id if active_task else '1'}-{timezone.now().strftime('%m%d%Y')}",
        'date': timezone.now().strftime("%B %d, %Y"),

        # NEW: expose saved LPO to template (optional UI use)
        'lpo_saved': lpo_saved,
    }

    return render(request, 'procurement_lpo_view.html', context)
# ======================================================================================================LPO END

from django.shortcuts import render
from .models import LPOTransaction

def lpo_list_view(request):
    lpos = LPOTransaction.objects.select_related(
        'project_task',
        'selected_quote',
        'selected_quote__supplier'
    ).order_by('-date_issued')

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
def print_memo_view(request, task_id):
    # This explicit name mapping resolves your AttributeError immediately
    active_task = get_object_or_404(ProjectTask, project_id=task_id)
    build_items = BOMItem.objects.filter(header__task=active_task)
    
    # Read values injected during the form routing pass
    winning_supplier = request.GET.get('winner', 'HABENGA HARDWARE SUPPLIER')
    materials_total = float(request.GET.get('mat', 0) or 0)
    labour_total = float(request.GET.get('labour', 0) or 0)
    misc_total = float(request.GET.get('misc', 0) or 0)
    
    grand_total = materials_total + labour_total + misc_total

    context = {
        'task': active_task,
        'build': build_items,
        'winning_supplier': winning_supplier,
        'materials_total': materials_total,
        'labour_total': labour_total,
        'misc_total': misc_total,
        'grand_total': grand_total,
    }
    return render(request, 'procurement_memo.html', context)
@login_required
def print_ro_view(request, ro_id):
    ro = get_object_or_404(RequisitionOrder, id=ro_id)
    return render(request, "ro_print_template.html", {"ro": ro, "items": ro.items.all()})

@login_required
def print_lpo_view(request, lpo_id):

    lpo = get_object_or_404(LPOTransaction, id=lpo_id)

    mat_b = lab_b = misc_b = Decimal("0.00")

    if lpo.variance_explanation:
        try:
            parts = lpo.variance_explanation.split('|')

            for p in parts:
                if "mat" in p.lower():
                    mat_b = Decimal(p.split(':')[1])
                elif "lab" in p.lower():
                    lab_b = Decimal(p.split(':')[1])
                elif "misc" in p.lower():
                    misc_b = Decimal(p.split(':')[1])
        except Exception:
            pass

    context = {
        'lpo': lpo,
        'mat_budget': mat_b,
        'lab_budget': lab_b,
        'misc_budget': misc_b,
        'total_budget': mat_b + lab_b + misc_b,
        'actual_spent': Decimal('0.00'),
        'bom_items': BOMItem.objects.filter(header__task=lpo.project_task)
    }

    return render(request, 'lpo_print_template.html', context)
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
    return render(request, 'rfq_print_letter.html', {
        'task': active_task,
        'today': timezone.now(),
        'supplier_packets': supplier_packets, # Directly feeds the {% for packet in supplier_packets %} loop
    })
# ======================================================================
@login_required
def print_bom_from_ro(request, ro_id):
    ro = get_object_or_404(RequisitionOrder, id=ro_id)
    bom = BOMHeader.objects.filter(ro=ro).first()

    if not bom:
        bom = BOMHeader.objects.create(task=ro.task, ro=ro, status='GENERATED')
        for item in ro.items.all():
            BOMItem.objects.create(
                header=bom,
                pillar_id=2,
                description=item.product.description if item.product else item.tech_spec_summary,
                qty=item.quantity,
                uom=item.uom,
                unit_price=0
            )

    return render(request, "bom_report_print.html", {
        "bom_no": bom.bom_id,
        "bom_items": bom.items.all(),
        "active_task": ro.task
    })
    
# ==========================================================
from decimal import Decimal
from django.contrib import messages
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.db import transaction
import uuid

from .models import ProjectTask, SupplierAccount, RFQTransaction, LPOTransaction, ProjectBudget, BudgetTransaction
from accounts.models import RequisitionOrder

def perform_procurement_sync(task, item, winner, runner, w_price, r_price, lpo_no):

    # 1. RFQ WINNER
    quote_record, _ = RFQTransaction.objects.update_or_create(
        bom_item_id=item.id,
        supplier=winner,
        defaults={
            'unit_cost_quoted': w_price,
            'is_selected': True
        }
    )

    # 2. RFQ RUNNER
    RFQTransaction.objects.update_or_create(
        bom_item_id=item.id,
        supplier=runner,
        defaults={
            'unit_cost_quoted': r_price,
            'is_selected': False
        }
    )

    # 3. LPO CREATION (UNCHANGED BUT SAFE)
    LPOTransaction.objects.create(
        lpo_no=lpo_no,
        selected_quote=quote_record,
        project_task=task,
        building=task.building,
        build_category=task.build_category,

        # 🔥 FIXED (PRINT COMPATIBILITY LAYER)
        variance_explanation=f"MAT:{w_price}|LAB:0|MISC:0"
    )

    # 4. 🧱 CRITICAL FIX: ENSURE BUDGET EXISTS + LOCKED
    ProjectBudget.objects.update_or_create(
        task=task,
        defaults={
            "status": "LOCKED"
        }
    )
# ===================================================================================

from django.http import HttpResponse


@login_required
def bid_evaluation_terminal_view(request):

    # =========================================================
    # LOAD ALL TASKS FIRST
    # =========================================================
    tasks = ProjectTask.objects.all()

    # =========================================================
    # RESOLVE ACTIVE TASK
    # =========================================================
    task_id = request.GET.get("task_id")

    active_task = None

    if task_id:
        active_task = ProjectTask.objects.filter(
            project_id=task_id
        ).first()

    # =========================================================
    # IF NO TASK SELECTED:
    # LOAD PAGE NORMALLY
    # =========================================================
    if not active_task:

        return render(request, "bid_evaluation.html", {
            "tasks": tasks,
            "active_task": None,
            "bom_items": [],
            "suppliers": SupplierAccount.objects.all(),
            "ro": [],
        })
 # ===============================================================================
 
from django.db.models import Sum, Avg
from .models import LPOTransaction

def get_historical_building_metrics(building_analysis_code):
    """
    Analyzes a specific building code across all past historical task structures
    to generate baseline estimates for future projects.
    """
    metrics = LPOTransaction.objects.filter(
        building_id=building_analysis_code
    ).values(
        'build_category__description', 
        'project_task__description'
    ).annotate(
        total_spent=Sum('selected_quote__unit_cost_quoted'),
        average_unit_rate=Avg('selected_quote__unit_cost_quoted')
    ).order_by('build_category')
    
    return metrics
# =============================================================procurement action endpoint.
from django.db import transaction
from django.shortcuts import redirect
from django.contrib import messages
from django.utils import timezone
from decimal import Decimal

@login_required
def treasury_commit_lpo(request):

    if request.method != "POST":
        return redirect("dashboard")

    task_id = request.POST.get("task_id")
    directive = request.POST.get("commit_action")

    active_task = ProjectTask.objects.filter(project_id=task_id).first()

    if not active_task:
        messages.error(request, "Invalid Task")
        return redirect("dashboard")

    # Example totals (replace with your BOM/RFQ calculation source)
    material_total = Decimal(request.POST.get("material_total", "0"))
    labour_total = Decimal(request.POST.get("labour_total", "0"))
    misc_total = Decimal(request.POST.get("misc_total", "0"))

    total_budget = material_total + labour_total + misc_total

    with transaction.atomic():

        budget, _ = ProjectBudget.objects.get_or_create(task=active_task)

        # =========================
        # 1. LOCK PATH
        # =========================
        if directive == "commit_v1":

            budget.material_total_cost = material_total
            budget.labour_burden = labour_total
            budget.misc_reserve = misc_total
            budget.total_authorized_budget = total_budget
            budget.status = "LOCKED"
            budget.save()

            # =========================
            # 2. CREATE LPO
            # =========================
            lpo = LPOTransaction.objects.create(
                lpo_no=f"LPO-{active_task.project_id}-{timezone.now().strftime('%Y%m%d%H%M%S')}",
                project_task=active_task,
                variance_explanation="Treasury Lock v1 approved baseline"
            )

            messages.success(request, f"LPO {lpo.lpo_no} issued successfully.")

            return redirect("print_lpo_view", lpo_id=lpo.id)

        # =========================
        # 3. AMEND PATH
        # =========================
        elif directive == "amend_v2":

            budget.status = "DRAFT"
            budget.version += 1
            budget.save()

            messages.warning(request, "Budget sent to amendment cycle v2.")

            return redirect(f"/bid-evaluation/?task_id={task_id}")

    return redirect("dashboard")
    
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
@login_required
def misc_purchase_builder(request):
    tasks = ProjectTask.objects.all()
    # 1. Always derive the task from the URL parameter first
    target_task_id = request.GET.get('task_id')
    active_task = tasks.filter(project_id=target_task_id).first() or tasks.first()
    
    # 2. Reset logic: Wipe session if we move to a different board
    if request.session.get('active_task_id') != active_task.project_id:
        request.session['batch_data'] = {'supplier': '', 'items': []}
        request.session['active_task_id'] = active_task.project_id
        request.session.modified = True

    # 3. Handle Form Submissions
    if request.method == "POST":
        if "update_supplier" in request.POST:
            request.session['batch_data']['supplier'] = request.POST.get('supplier', '')
        elif "add_misc_purchase" in request.POST:
            qty = float(request.POST.get('qty', 0))
            price = float(request.POST.get('unit_price', 0))
            request.session['batch_data']['items'].append({
                'description': request.POST.get('description'),
                'uom': request.POST.get('uom'),
                'qty': qty,
                'unit_price': price,
                'total': qty * price
            })
        elif "delete_item" in request.POST:
            idx = int(request.POST.get('index'))
            request.session['batch_data']['items'].pop(idx)
        
        request.session.modified = True
        # IMPORTANT: Redirect forces the browser back to the specific task URL
        return redirect(f'/misc-purchase/?task_id={active_task.project_id}')

    # 4. Calculation
    actual = sum(float(i['total']) for i in request.session['batch_data']['items'])
    budget_x = 120000.00

    return render(request, 'misc_purchase.html', {
        'tasks': tasks,
        'active_task': active_task,
        'batch': request.session['batch_data'],
        'budget_x': budget_x,
        'actual': actual,
        'variance': budget_x - actual
    })
    
# =================================================================

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.utils import timezone
# from .models import ProjectTask, MiscPurchaseOrder, MiscPurchaseItem

@login_required
def ad_hoc_purchase_memo_view(request):
    """
    Renders the Executive Memo for the GM.
    Reads from the active session draft before it hits the database.
    """
    target_task_id = request.GET.get('task_id')
    active_task = get_object_or_404(ProjectTask, project_id=target_task_id)
    
    # Pull current draft from session
    batch = request.session.get('batch_data', {'supplier': '', 'items': []})
    actual = sum(float(i['total']) for i in batch['items'])
    
    # Example fixed budget - replace with your actual budget field if dynamic
    budget_x = 120000.00 
    variance = budget_x - actual

    return render(request, 'ad_hoc_purchase_memo.html', {
        'active_task': active_task,
        'batch': batch,
        'actual': actual,
        'budget_x': budget_x,
        'variance': variance
    })
    
# =================================================
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from .models import ProjectTask

@login_required
def print_fluid_ro_view(request):
    """
    The Plumbing: Connects session data to the printable scouting document.
    """
    # 1. Get the Task (ensuring we are scoped to the right project)
    task_id = request.GET.get('task_id')
    active_task = get_object_or_404(ProjectTask, project_id=task_id)
    
    # 2. Extract the 'Fluid' draft
    batch = request.session.get('batch_data', {'items': [], 'supplier': ''})
    actual = sum(float(i['total']) for i in batch['items'])
    
    # 3. Handle the Temp RO ID (The ID persists as long as the session lives)
    temp_ro_id = request.session.get('temp_ro_id')
    if not temp_ro_id:
        # Generate new ID if this is the start of a scouting run
        temp_ro_id = f"TMP-{timezone.now().strftime('%y%m%d%H%M')}"
        request.session['temp_ro_id'] = temp_ro_id
    
    # 4. Return to the printer-friendly template
    return render(request, 'print_mpo.html', {
        'batch': batch,
        'temp_ro_id': temp_ro_id,
        'actual': actual,
        'active_task': active_task,
    })

@login_required
def print_mpo_view(request, mpo_id):
    """
    Renders the black-and-white, ink-friendly requisition letter.
    """
    mpo = get_object_or_404(MiscPurchaseOrder, id=mpo_id)
    
    return render(request, 'print_mpo.html', {
        'mpo': mpo,
        'active_task': mpo.task,
        'items': mpo.items.all(),
        'actual': mpo.total_amount,
    })
# ========================================================================== Budget
from django.shortcuts import render
from django.db.models import Sum
from decimal import Decimal

from .models import ProjectBudget, PaymentOrder
from django.db.models import Sum, F, DecimalField, ExpressionWrapper

def budget_overview(request):
    budgets = ProjectBudget.objects.select_related('task').all()

    rows = []

    for b in budgets:

        actual_qs = PaymentOrder.objects.filter(
            grn__lpo__project_task=b.task,
            is_confirmed_by_director=True
        )

        actual = actual_qs.aggregate(
            total=Sum(
                ExpressionWrapper(
                    F('grn__lpo__selected_quote__unit_cost_quoted') *
                    F('grn__lpo__selected_quote__quantity'),
                    output_field=DecimalField()
                )
            )
        )['total'] or 0

        budget_value = float(b.total_authorized_budget or 0)
        actual_value = float(actual or 0)

        rows.append({
            "task_id": b.task.project_id if b.task else "N/A",
            "budget_label": b.budget_label,
            "budget": budget_value,
            "actual": actual_value,
            "variance": budget_value - actual_value,
        })

    return render(request, 'budget_overview.html', {
        'rows': rows
    })
   
# ============================================================================

@login_required
def misc_budget_actuals_view(request):
    """
    Renders the executive financial dashboard showing what is locked.
    """
    target_task_id = request.GET.get('task_id')
    active_task = get_object_or_404(ProjectTask, project_id=target_task_id)
    
    # Query ONLY funds that have been authorized, disbursed, or reconciled
    locked_audit_trail = MiscPurchaseOrder.objects.filter(
        task=active_task, 
        status__in=['AUTHORIZED', 'DISBURSED', 'RECONCILED']
    ).order_by('-authorized_at')
    
    misc_actuals = sum(mpo.total_amount for mpo in locked_audit_trail)
    misc_budget = 120000.00 # Replace with active_task.budget if you have it mapped
    
    return render(request, 'misc_budget_actuals.html', {
        'active_task': active_task,
        'locked_audit_trail': locked_audit_trail,
        'misc_budget': misc_budget,
        'misc_actuals': misc_actuals,
        'variance': misc_budget - misc_actuals
    })
    
    
# ======================================================

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from .models import MiscPurchaseOrder, MiscPurchaseItem # Ensure you import your models

def authorize_mpo_action(request):
    if request.method == "POST":
        # 1. Get the fluid session data
        batch = request.session.get('batch_data', {'items': [], 'supplier': ''})
        
        if not batch.get('items'):
            messages.error(request, "No items found to authorize.")
            return redirect('misc_purchase_builder')

        # 2. Logic to create the permanent record
        # Note: Replace 'active_task' logic as per your specific project model
        mpo = MiscPurchaseOrder.objects.create(
            # Add your fields here, e.g., supplier=batch['supplier']
            status='LOCKED'
        )
        
        # 3. Create the items
        for item in batch['items']:
            MiscPurchaseItem.objects.create(
                mpo=mpo,
                description=item['description'],
                qty=item['qty'],
                unit_price=item['unit_price']
            )
            
        # 4. Clear the fluid session
        request.session['batch_data'] = {'items': [], 'supplier': ''}
        request.session['temp_ro_id'] = None
        
        # 5. Redirect to the final print view
        return redirect('print_mpo', mpo_id=mpo.id)
        
    return redirect('misc_purchase_builder')
    
# ====================================================
from django.db.models import Sum
from .models import MiscRequisitionOrder, ProjectTask

def misc_budget_actuals_view(request):
    # 1. Fetch the task (adjust the filter/ID retrieval as needed for your specific setup)
    task_id = request.session.get('active_task_id')
    active_task = get_object_or_404(ProjectTask, pk=task_id)
    
    # 2. Define the static budget number
    # Replace 100000.00 with your actual constant budget figure
    STATIC_MISC_BUDGET = 100000.00 
    
    # 3. Calculate actuals from the MRO model
    mros = MiscRequisitionOrder.objects.filter(task=active_task)
    total_locked = mros.filter(
        funding_status__in=['LOCKED', 'DISBURSED', 'RECONCILED']
    ).aggregate(Sum('total_amount'))['total_amount__sum'] or 0
    
    context = {
        'active_task': active_task,
        'misc_budget': STATIC_MISC_BUDGET,
        'misc_actuals': total_locked,
        'variance': STATIC_MISC_BUDGET - total_locked,
        'locked_audit_trail': mros.order_by('-updated_at'),
    }
    
    return render(request, 'misc_budget_actuals.html', context)
    
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
            selected_quote=rfq,
            project_task=task,
            variance_explanation="System-triggered chain update"
        )
        return lpo
        
from django.shortcuts import render, get_object_or_404
from decimal import Decimal
from .models import LPOTransaction, BOMItem


def print_lpo_view(request, lpo_id):
    lpo = get_object_or_404(LPOTransaction, id=lpo_id)

    # Try to safely extract variance breakdown if it exists
    try:
        parts = lpo.variance_explanation.split('|')

        mat_budget = Decimal(parts[0].split(':')[1])
        lab_budget = Decimal(parts[1].split(':')[1])
        misc_budget = Decimal(parts[2].split(':')[1])

    except Exception:
        mat_budget = Decimal('0.00')
        lab_budget = Decimal('0.00')
        misc_budget = Decimal('0.00')

    bom_items = BOMItem.objects.filter(header__task=lpo.project_task)

    context = {
        "lpo": lpo,
        "lpo_no": lpo.lpo_no,
        "date": lpo.created_at if hasattr(lpo, "created_at") else lpo.date_issued,

        "task": lpo.project_task,
        "supplier_account": lpo.selected_quote.supplier if lpo.selected_quote else None,

        "items": bom_items,

        "mat_budget": mat_budget,
        "lab_budget": lab_budget,
        "misc_budget": misc_budget,
        "total_budget": mat_budget + lab_budget + misc_budget,

        "materials_total": lpo.selected_quote.unit_cost_quoted if lpo.selected_quote else 0,
    }

    return render(request, "procurement_lpo.html", context)
    
    
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