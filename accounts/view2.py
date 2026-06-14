from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.contrib.auth.models import User
from django.contrib import messages
from django.http import JsonResponse, HttpResponseForbidden
from django.forms.models import model_to_dict
from django.apps import apps
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Sum
from decimal import Decimal
from django.utils import timezone
from .models import (
    UserAccount, 
    UserCategory, 
    # ... other models ...
    RequisitionOrder, 
    RequisitionOrderItem,
    LPOTransaction,
    RFQTransaction  # <--- YOU MUST ADD THIS LINE
)

# At the top of accounts/views.py
from .models import (
    UserAccount, 
    UserCategory, 
    BankAccount, 
    SupplierAccount, 
    GLAccount, 
    GLAnalysisCategory, 
    ProjectTask, 
    ProjectBuildCategory, 
    Product, 
    ProjectBuilding,
    BOMHeader,           # Ensure this is here
    BOMItem,             # Ensure this is here
    RequisitionOrder,    # <--- THIS IS THE ONE MISSING
    RequisitionOrderItem # <--- AND THIS ONE
)

# ===============================
# 🔐 AUTH & ACCESS
# ===============================
class CustomLoginView(LoginView):
    template_name = 'login.html'
    redirect_authenticated_user = True

def has_module_access(user, module_code):
    try:
        return user.useraccount.access_level.modules.filter(code=module_code).exists()
    except:
        return False

# ===============================
# 🏠 NAVIGATION
# ===============================
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
 
 
 # ==============================xxxxxx======================
 # ===============================
# 🚀 PIONEER UNIFIED TRAFFIC CONTROLLER (CRUD ENGINE)
# ===============================

def get_pioneer_model(entity_type):
    """Helper to map URL strings to actual Model classes from your models.py"""
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
        # ADD THESE TWO LINES:
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
        
        # Extract data excluding metadata
        data = {k: v for k, v in request.POST.items() if k not in ['mode', 'original_id', 'csrfmiddlewaretoken']}
        
        try:
            if mode == "edit" and original_id:
                obj = get_object_or_404(model, pk=original_id)
                for key, value in data.items():
                    setattr(obj, key, value)
                obj.save()
                msg = f"{entity_type.upper()} updated successfully."
            else:
                # Standard create for your Master Files
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
 
 # ============================gggggg==============
 # ... (Keep your existing imports and dashboard view above) ...

@login_required
def create_user(request):
    """
    Handles the creation of a User and their corresponding UserAccount.
    """
    if request.method == "POST":
        # 1. Capture names, system credentials, and the new Staff Number
        staff_no = request.POST.get('staff_no') # <--- CAPTURE NEW FIELD
        first_name = request.POST.get('first_name', '')
        last_name = request.POST.get('last_name', '')
        username = request.POST.get('username')
        email = request.POST.get('email')
        cat_id = request.POST.get('access_level_id')

        try:
            # 2. Handle the Django Auth User
            user, created = User.objects.get_or_create(username=username)
            if email:
                user.email = email
            user.save()

            # 3. Resolve the Category (CAT)
            category = None
            if cat_id:
                category = UserCategory.objects.filter(id=cat_id).first()

            # 4. Create/Update the UserAccount (The Pioneer Profile)
            UserAccount.objects.update_or_create(
                user=user,
                defaults={
                    'staff_no': staff_no, # <--- ADD TO DEFAULTS
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
            # If staff_no is not unique, this catch will return the database error
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

    return HttpResponseForbidden("Method not allowed")
 # ==============================xxxxxx======================
 
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.forms.models import model_to_dict

# IMPORT ALL MODELS ACCORDING TO YOUR PROVIDED MODELS.PY
from .models import (
    ProjectTask, BOMHeader, BOMItem, Product, SupplierAccount,
    LPOTransaction, GRNTransaction, PaymentOrder, ProjectBuildCategory,
    BankAccount, GLAccount, GLAnalysisCategory, ProjectBuilding, UserAccount, UserCategory
)

# 1. Dashboard View
@login_required
def fin_mgmt_ops_view(request):
    # Matches ProjectTask(project_id, description)
    tasks = ProjectTask.objects.all()
    context = {
        'page_title': 'Pioneer Financial Ops',
        'tasks': tasks,
        'mtd_actuals': "89,200.00", # Placeholder for actual spent logic
    }
    return render(request, 'Fin_Mgmt_and_OPs_dashboard.html', context)

# =======================================================================
import re



def generate_ro_no():
    last = RequisitionOrder.objects.all().order_by('id').last()

    if not last or not last.ro_no:
        return "RO No. 001"

    match = re.search(r'(\d+)', last.ro_no)

    if match:
        next_num = int(match.group(1)) + 1
        return f"RO No. {str(next_num).zfill(3)}"

    return "RO No. 001"

# =======================================================================
def ro_builder_view(request):

    tasks = ProjectTask.objects.all()

    task_id = request.GET.get("task_id")
    active_task = ProjectTask.objects.filter(project_id=task_id).first()

    if not active_task:
        active_task = tasks.first()

    # ---------------------------------------------------
    # GET OR CREATE RO (SAFE + STABLE)
    # ---------------------------------------------------
    ro = RequisitionOrder.objects.filter(
        task=active_task,
        status="DRAFT"
    ).first()

    if not ro:
        ro = RequisitionOrder.objects.create(
            task=active_task,
            ro_no=generate_ro_no(),
            created_by=None,
            status="DRAFT"
        )

    # ---------------------------------------------------
    # ADD ITEM TO RO
    # ---------------------------------------------------
    if request.method == "POST" and "add_item" in request.POST:

        description = request.POST.get("description")
        uom = request.POST.get("uom")
        qty = request.POST.get("qty")

        if description and qty:

            RequisitionOrderItem.objects.create(
                ro=ro,
                product=None,  # optional linking later
                quantity=qty,
                uom=uom,
                tech_spec_summary=description
            )

        return redirect(f"/ro-builder/?task_id={active_task.project_id}")

    # ---------------------------------------------------
    # LOAD RO ITEMS
    # ---------------------------------------------------
    ro_items = ro.items.all().order_by("id")

    # ---------------------------------------------------
    # RENDER RO VIEW (NO BOM LOGIC HERE)
    # ---------------------------------------------------
    return render(request, "RO_builder.html", {
        "tasks": tasks,
        "active_task": active_task,
        "ro": ro,
        "ro_no": ro.ro_no,
        "ro_items": ro_items,
    })
# =======================================================================xxx1 

# 2. STEP 1: BOM Builder (Site Manager)
@login_required
def bom_builder_view(request):
    tasks = ProjectTask.objects.all()
    selected_id = request.GET.get('task_id')
    # Uses 'project_id' as the PK per your model
    active_task = ProjectTask.objects.filter(project_id=selected_id).first() or tasks.first()

    # Bridge to BOMHeader(task, status)
    bom_header, created = BOMHeader.objects.get_or_create(
        task=active_task,
        defaults={'status': 'DRAFT'}
    )

    if request.method == "POST" and "add_item" in request.POST:
        # Matches BOMItem(header, pillar_id, description, qty, uom)
        BOMItem.objects.create(
            header=bom_header,
            pillar_id=2, 
            description=request.POST.get('description'),
            qty=request.POST.get('qty', 0),
            uom=request.POST.get('uom', 'Pcs')
        )
        return redirect(f'/bom-builder/?task_id={active_task.project_id}')

    bom_items = bom_header.items.all().order_by('id')
    context = {
        'tasks': tasks,
        'active_task': active_task,
        'bom_items': bom_items,
        'bom_no': bom_header.bom_id,
    }
    return render(request, 'bom_builder.html', context)
    
# =================================================================xxxx1 ===ro_builder_view

@login_required
def ro_builder(request):
    """
    STEP 2: Financial Request (Accountant/GM)
    This view manages the creation and item listing for Requisition Orders.
    """
    tasks = ProjectTask.objects.all()
    task_id = request.GET.get("task_id")
    
    # Get the task or default to the first one
    active_task = ProjectTask.objects.filter(project_id=task_id).first() or tasks.first()

    # Get or create the RO for this task
    ro, created = RequisitionOrder.objects.get_or_create(
        task=active_task,
        status="DRAFT",
        defaults={'ro_no': f"RO-{timezone.now().strftime('%m%d%H%M')}"}
    )

    # Logic for adding items manually via the Modal
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
        "ro_items": ro.items.all().order_by("id"),
    })
# ============================================================================


def bom_from_ro_print(request, ro_id):
    ro = RequisitionOrder.objects.get(id=ro_id)

    # 1. Check if BOM already exists for this RO
    bom = BOMHeader.objects.filter(ro=ro).first()

    # 2. If not, generate it (LOCKED SNAPSHOT MODEL)
    if not bom:
        bom = BOMHeader.objects.create(
            task=ro.task,
            ro=ro,
            status="GENERATED"
        )

        # 3. Copy RO items → BOM snapshot
        for item in ro.items.all():
            BOMItem.objects.create(
                header=bom,
                description=item.product.description,
                qty=item.quantity,
                uom=item.uom
            )

    return render(request, "bom_report_print.html", {
        "bom_no": bom.bom_id,
        "bom_items": bom.items.all(),
        "active_task": ro.task
    })

# =================================================================
def print_bom_from_ro(request, ro_id):

    ro = RequisitionOrder.objects.get(id=ro_id)

    # CHECK IF BOM EXISTS
    bom = BOMHeader.objects.filter(ro=ro).first()

    # CREATE BOM FROM RO
    if not bom:

        bom = BOMHeader.objects.create(
            task=ro.task,
            ro=ro,
            status='GENERATED'
        )

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
# ================================================================= 222 to 333

@login_required
def print_ro_view(request, ro_id):
    """
    This is the missing function! 
    It fetches the RO data and sends it to your 'ro.html' template.
    """
    from django.shortcuts import get_object_or_404
    
    # 1. Get the Requisition Order from the database
    ro = get_object_or_404(RequisitionOrder, id=ro_id)
    
    # 2. Render it using your existing 'ro.html' file
    return render(request, "ro.html", {
        "ro": ro,
        "items": ro.items.all()
    })

# =================================================================




from django.shortcuts import get_object_or_404 # Ensure this is at the top of your file

@login_required
def fetch_bom_to_ro(request, ro_id):
    """
    This is the missing function causing the AttributeError.
    It pulls items FROM the BOM INTO the RO.
    """
    ro = get_object_or_404(RequisitionOrder, id=ro_id)
    # Find the Technical BOM for this project
    bom = BOMHeader.objects.filter(task=ro.task).first()
    
    if bom:
        for item in bom.items.all():
            # Stitch the technical data to the financial order
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
def print_ro_view(request, ro_id):
    """
    Another missing function required by your new URLs.
    """
    ro = get_object_or_404(RequisitionOrder, id=ro_id)
    return render(request, "ro_print_template.html", {"ro": ro})


# =================================================================

# 3. STEP 2: Procurement (GM)
@login_required
def procurement_lpo_view(request):
    # --- 1. SETUP CONTEXT ---
    tasks = ProjectTask.objects.all()
    selected_id = request.GET.get('task_id')
    active_task = ProjectTask.objects.filter(project_id=selected_id).first() or tasks.first()
    
    suppliers = SupplierAccount.objects.all().order_by('description')
    bom_header = BOMHeader.objects.filter(task=active_task).first()
    
    # We ensure these are the actual line items linked to the BOM Header
    bom_items = bom_header.items.all() if bom_header else []

    # --- 2. HANDLE POST REQUEST (LPO GENERATION) ---
    if request.method == "POST" and "generate_lpo" in request.POST:
        vendor_name = request.POST.get('supplier_name')
        
        # Safe decimal conversion
        try:
            unit_price = Decimal(request.POST.get('unit_price', 0) or 0)
            misc_budget = Decimal(request.POST.get('misc_expenses', 0) or 0)
        except:
            unit_price = Decimal('0.00')
            misc_budget = Decimal('0.00')
        
        # VALIDATION: Cannot create an LPO without BOM items
        if not bom_items.exists():
            messages.error(request, "Error: You cannot issue an LPO for a task with an empty BOM.")
            return redirect(f'/procurement/?task_id={active_task.project_id}')

        # A. Resolve Supplier
        supplier, _ = SupplierAccount.objects.get_or_create(
            description__iexact=vendor_name,
            defaults={
                'supplier_id': f"SUP-{timezone.now().strftime('%y%m%d%H%M')}",
                'description': vendor_name
            }
        )

        # B. Financial Logic & RFQ Creation (The "Fast-Track" Loop)
        mat_total = Decimal('0.00')
        winning_quote = None  # We will use the last created quote as the LPO anchor

        for item in bom_items:
            # Calculate item total
            item_qty = Decimal(item.qty or 0)
            mat_total += (item_qty * unit_price)

            # Create the RFQ for EVERY item to satisfy NOT NULL constraints
            winning_quote = RFQTransaction.objects.create(
                rfq_no=f"RFQ-{item.id}-{timezone.now().strftime('%H%M%S')}",
                bom_item=item,  # Links to the actual BOMTransaction record
                supplier=supplier,
                unit_cost_quoted=unit_price,
                is_selected=True
            )

        # C. Labor Calculation (25% Rule)
        lab_total = (mat_total * Decimal('0.25')).quantize(Decimal('0.01'))
        
        # D. Final LPO Record Creation
        new_lpo = LPOTransaction.objects.create(
            lpo_no=f"LPO-{active_task.project_id}-{timezone.now().strftime('%m%d%H')}",
            selected_quote=winning_quote,  # Anchor quote
            project_task=active_task,
            building=ProjectBuilding.objects.first(),
            build_category=ProjectBuildCategory.objects.first(),
            # The 'DNA String' for the print report
            variance_explanation=f"MAT:{mat_total}|LAB:{lab_total}|MISC:{misc_budget}"
        )

        # E. Finish: Send user straight to the print view
        messages.success(request, f"LPO {new_lpo.lpo_no} generated successfully.")
        return redirect('print_lpo_view', lpo_id=new_lpo.id)

    # --- 3. RENDER THE INPUT FORM ---
    return render(request, 'procurement_lpo.html', {
        'tasks': tasks,
        'active_task': active_task,
        'bom_items': bom_items,
        'bom_no': bom_header.bom_id if bom_header else "N/A",
        'suppliers': suppliers
    })
	
# ==========================================================================

@login_required
def print_lpo_view(request, lpo_id):
    lpo = get_object_or_404(LPOTransaction, id=lpo_id)
    
    # Extract Budget from the "DNA string" we saved in variance_explanation
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
        'actual_spent': Decimal('0.00'), # Baseline for a new LPO
        'bom_items': BOMItem.objects.filter(header__task=lpo.project_task)
    }
    return render(request, 'lpo_print_template.html', context)
# =========================AUTO SEARCH !!

@login_required
def supplier_lookup(request):
    term = request.GET.get('term', '')
    
    # We only search if they've typed at least 2 letters
    if len(term) >= 2:
        # Search the description field for the partial match
        suppliers = SupplierAccount.objects.filter(
            description__icontains=term
        )[:10] # Top 10 results for speed
        
        results = [
            {'id': s.supplier_id, 'value': s.description} 
            for s in suppliers
        ]
        return JsonResponse(results, safe=False)
        
    return JsonResponse([], safe=False)


# ===================================== end

# 4. STEP 3: Settlement (Site Mgr & Director)
@login_required
def payment_settlement_view(request):
    tasks = ProjectTask.objects.all()
    selected_id = request.GET.get('task_id')
    active_task = ProjectTask.objects.filter(project_id=selected_id).first() or tasks.first()
    
    # Matches LPOTransaction(project_task=active_task)
    pending_grns = LPOTransaction.objects.filter(project_task=active_task)
    pending_payments = GRNTransaction.objects.filter(lpo__project_task=active_task)

    if request.method == "POST":
        # Recording GRN (Site Manager)
        if "record_grn" in request.POST:
            lpo = get_object_or_404(LPOTransaction, id=request.POST.get('lpo_id'))
            # Matches GRNTransaction(grn_no, lpo, delivery_note_ref, qty_received, received_by)
            GRNTransaction.objects.create(
                grn_no=f"GRN-{timezone.now().strftime('%y%m%d%H%M')}",
                lpo=lpo,
                delivery_note_ref=request.POST.get('dn_ref'),
                qty_received=request.POST.get('qty_received'),
                received_by=request.user
            )
            messages.success(request, "GRN Successfully Recorded.")

        # Processing Payment (Director)
        elif "process_payment" in request.POST:
            grn = get_object_or_404(GRNTransaction, id=request.POST.get('grn_id'))
            # Matches PaymentOrder(pay_order_no, grn, payment_method, source_bank, is_confirmed_by_director)
            PaymentOrder.objects.create(
                pay_order_no=f"PAY-{timezone.now().strftime('%y%m%d%H%M')}",
                grn=grn,
                payment_method=request.POST.get('method'),
                source_bank_id=request.POST.get('bank_id'),
                is_confirmed_by_director=True,
                date_confirmed=timezone.now()
            )
            messages.success(request, "Director Payment Confirmed.")
            
        return redirect(f'/payment-settlement/?task_id={active_task.project_id}')

    context = {
        'tasks': tasks,
        'active_task': active_task,
        'pending_grns': pending_grns,
        'pending_payments': pending_payments,
    }
    return render(request, 'payment_settlement.html', context)
    
