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
    RFQTransaction, GRNTransaction, PaymentOrder
)

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
@login_required
def bid_evaluation_view(request):
    task_id = request.GET.get('task_id')
    active_task = get_object_or_404(ProjectTask, project_id=task_id)
    pending_rfqs = RFQTransaction.objects.filter(bom_item__header__task=active_task).select_related('supplier', 'bom_item')

    if request.method == "POST":
        for rfq in pending_rfqs:
            price_field = f"price_{rfq.id}"
            if price_field in request.POST:
                rfq.unit_cost_quoted = Decimal(request.POST.get(price_field) or 0)
                rfq.save()

        winner = pending_rfqs.order_by('unit_cost_quoted').first()
        if winner and winner.unit_cost_quoted > 0:
            RFQTransaction.objects.filter(bom_item__header__task=active_task, supplier=winner.supplier).update(is_selected=True)
            RFQTransaction.objects.filter(bom_item__header__task=active_task).exclude(supplier=winner.supplier).update(is_selected=False)
            
            messages.success(request, f"System Evaluation Complete: {winner.supplier.description} Selected.")
            return redirect(f"/budget-approval/?task_id={task_id}")

    return render(request, 'bid_evaluation.html', {
        'active_task': active_task,
        'rfqs': pending_rfqs
    })

# =======================================================================
# 💰 PROCUREMENT, LPO & FINANCIAL SETTLEMENT TRANSACTIONS
# =======================================================================
@login_required
def procurement_lpo(request):
    """Unified single logic layout called directly from urls.py line 64."""
    tasks = ProjectTask.objects.all()
    selected_id = request.GET.get('task_id')
    active_task = ProjectTask.objects.filter(project_id=selected_id).first() or tasks.first()
    
    suppliers = SupplierAccount.objects.all().order_by('description')
    bom_header = BOMHeader.objects.filter(task=active_task).first()
    bom_items = bom_header.items.all() if bom_header else BOMItem.objects.none()

    if request.method == "POST" and "generate_lpo" in request.POST:
        vendor_name = request.POST.get('supplier_name')
        
        try:
            unit_price = Decimal(request.POST.get('unit_price', 0) or 0)
            misc_budget = Decimal(request.POST.get('misc_expenses', 0) or 0)
        except:
            unit_price = misc_budget = Decimal('0.00')
        
        if not bom_items.exists():
            messages.error(request, "Error: You cannot issue an LPO for a task with an empty BOM.")
            return redirect(f'/procurement/?task_id={active_task.project_id}')

        supplier, _ = SupplierAccount.objects.get_or_create(
            description__iexact=vendor_name,
            defaults={
                'supplier_id': f"SUP-{timezone.now().strftime('%y%m%d%H%M')}",
                'description': vendor_name
            }
        )

        mat_total = Decimal('0.00')
        winning_quote = None

        for item in bom_items:
            item_qty = Decimal(item.qty or 0)
            mat_total += (item_qty * unit_price)

            winning_quote = RFQTransaction.objects.create(
                rfq_no=f"RFQ-{item.id}-{timezone.now().strftime('%H%M%S')}",
                bom_item=item,
                supplier=supplier,
                unit_cost_quoted=unit_price,
                is_selected=True
            )

        lab_total = (mat_total * Decimal('0.25')).quantize(Decimal('0.01'))
        
        new_lpo = LPOTransaction.objects.create(
            lpo_no=f"LPO-{active_task.project_id}-{timezone.now().strftime('%m%d%H')}",
            selected_quote=winning_quote,
            project_task=active_task,
            building=ProjectBuilding.objects.first(),
            build_category=ProjectBuildCategory.objects.first(),
            variance_explanation=f"MAT:{mat_total}|LAB:{lab_total}|MISC:{misc_budget}"
        )

        messages.success(request, f"LPO {new_lpo.lpo_no} generated successfully.")
        return redirect('print_lpo_view', lpo_id=new_lpo.id)

    return render(request, 'procurement_lpo.html', {
        'tasks': tasks,
        'active_task': active_task,
        'bom_items': bom_items,
        'bom_no': bom_header.bom_id if bom_header else "N/A",
        'suppliers': suppliers
    })

@login_required
def payment_settlement_view(request):
    """Renders the master ledger of all committed Payment Orders."""
    tasks = ProjectTask.objects.all()
    selected_id = request.GET.get('task_id')
    active_task = ProjectTask.objects.filter(project_id=selected_id).first()
    
    payments = PaymentOrder.objects.all().order_by('-id')
    if active_task:
        payments = payments.filter(lpo__project_task=active_task)

    return render(request, 'payment_settlement.html', {
        'tasks': tasks,
        'active_task': active_task,
        'payments': payments,
    })

# =======================================================================
# 🖨️ CLEAN UNIFIED DOCUMENTATION PRINT VISUALIZERS
# =======================================================================
@login_required
def print_memo_view(request, task_id):
    """Your precise custom disbursement memo layout tracking query variables perfectly."""
    active_task = get_object_or_404(ProjectTask, project_id=task_id)
    build_items = BOMItem.objects.filter(header__task=active_task)
    
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
    try:
        parts = lpo.variance_explanation.split('|')
        mat_b = Decimal(parts[0].split(':')[1])
        lab_b = Decimal(parts[1].split(':')[1])
        misc_b = Decimal(parts[2].split(':')[1])
    except:
        mat_b = lab_b = misc_b = Decimal('0.00')

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
    Tail-end single execution print engine mapped directly to the 
    tokens provided in your custom rfq_print_letter.html file.
    """
    # 1. Extract query parameters from your dashboard selection context
    task_id = request.GET.get('task_id')
    supplier_id = request.GET.get('supplier_id')
    
    # 2. Fetch the target database model records securely
    active_task = get_object_or_404(ProjectTask, project_id=task_id)
    supplier = get_object_or_404(SupplierAccount, supplier_id=supplier_id)
    
    # 3. Locate the completed Technical Order (RO) built by your Site Manager
    ro = RequisitionOrder.objects.filter(task=active_task).first()
    
    # 4. Extract lines from the working RO layer to guarantee property match 
    # with {{ item.tech_spec_summary }} and {{ item.quantity }} tokens
    if ro:
        items_payload = ro.items.all().order_by('id')
        display_ro_no = ro.ro_no
    else:
        # Graceful fallback protection if data is parsed before RO creation step
        display_ro_no = f"RFQ-{active_task.project_id}"
        items_payload = []
    
    # 5. Hand variables directly over to your exact template layout
    return render(request, 'rfq_print_letter.html', {
        'task': active_task,            # Maps to {{ task.project_id }} & {{ task.description }}
        'supplier': supplier,          # Maps to {{ supplier.description }} & {{ supplier.address }}
        'ro_no': display_ro_no,        # Maps to {{ ro_no }}
        'today': timezone.now(),       # Maps to {{ today|date:"d M Y" }}
        'items': items_payload,        # Maps to {% for item in items %} loop
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