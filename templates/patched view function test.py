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

            selected_quote=quote_record,

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

from django.http import HttpResponse


@login_required
def bid_evaluation_terminal_view(request):

    # =========================================================
    # TASK RESOLUTION (SAFE)
    # =========================================================
    task_id = request.GET.get("task_id")

    active_task = (
        ProjectTask.objects.filter(project_id=task_id).first()
        if task_id
        else ProjectTask.objects.first()
    )

    # =========================================================
    # HARD SAFETY CHECK
    # =========================================================
    if not active_task:
        messages.error(request, "No active project task found.")
        return redirect("dashboard")

    # =========================================================
    # LOAD SUPPLIERS
    # =========================================================
    suppliers = SupplierAccount.objects.all()

    # =========================================================
    # PROCUREMENT SOURCE 1 — BOM
    # =========================================================
    bom_items = BOMTransaction.objects.filter(
        project_task=active_task
    ).select_related("product")

    # =========================================================
    # PROCUREMENT SOURCE 2 — RO
    # =========================================================
    ro_items = RequisitionOrderItem.objects.filter(
        ro__task=active_task
    ).select_related("product")

    # =========================================================
    # PROCUREMENT SOURCE 3 — RFQ
    # =========================================================
    rfq_items = RFQTransaction.objects.filter(
        bom_item__project_task=active_task
    ).select_related(
        "bom_item",
        "bom_item__product",
        "supplier"
    )

    # =========================================================
    # FALLBACK PROCUREMENT RESOLUTION
    # =========================================================
    source_type = "EMPTY"
    final_items = []

    if bom_items.exists():

        final_items = bom_items
        source_type = "BOM"

    elif ro_items.exists():

        final_items = ro_items
        source_type = "RO"

    elif rfq_items.exists():

        final_items = rfq_items
        source_type = "RFQ"

    # =========================================================
    # LOAD BUDGET
    # =========================================================
    budget = ProjectBudget.objects.filter(
        task=active_task
    ).first()


    if request.method == "POST":
        # 1. Capture Form Data
        material_val = request.POST.get('material_total')
        labour_val = request.POST.get('labour_input')
        misc_val = request.POST.get('misc_input')
        grand_total = request.POST.get('grand_total')

        # 2. Update/Create ProjectBudget
        budget, _ = ProjectBudget.objects.get_or_create(
            task=active_task,
            defaults={'budget_label': f"Budget-{active_task.project_id}"}
        )
        budget.material_total_cost = material_val
        budget.labour_burden = labour_val
        budget.misc_reserve = misc_val
        budget.total_authorized_budget = grand_total
        budget.save()

        # 3. Create BudgetTransactions for the audit trail
        BudgetTransaction.objects.create(budget=budget, category='MATERIAL', amount=material_val, description="Initial Material Baseline")
        BudgetTransaction.objects.create(budget=budget, category='LABOUR', amount=labour_val, description="Labour Burden")
        BudgetTransaction.objects.create(budget=budget, category='MISC', amount=misc_val, description="Misc Reserve")

        # 4. Redirect to LPO/Procurement Flow
         # =========================================================
    # LOAD EXISTING LPOS (OPTIONAL SAFE LOAD)
    # =========================================================
    lpos = LPOTransaction.objects.filter(
        project_task=active_task
    ).select_related(
        "selected_quote",
        "selected_quote__supplier"
    )

    # =========================================================
    # TASK COLLECTION FOR DROPDOWN
    # =========================================================
    tasks = ProjectTask.objects.all()

    # =========================================================
    # RENDER
    # =========================================================
    return render(request, "bid_evaluation.html", {

        # ACTIVE STATE
        "active_task": active_task,
        "tasks": tasks,
        # Since your LPOTransaction model requires a 'selected_quote', 
        # ensure your form passes the selected_quote_id
        return redirect('procurement_authorization', task_id=active_task.project_id)
        
        
        
    

    return render(request, "bid_evaluation.html", {
        "active_task": active_task,
        "tasks": ProjectTask.objects.all(),
        "bom_items": BOMItem.objects.filter(header__project_task=active_task),
        "suppliers": SupplierAccount.objects.all(),
    })
    
 =====================================================================================