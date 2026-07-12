# ============================================================================
# BUILDWATCH ADDENDUM A — add these views to accounts/views.py
# ============================================================================

from decimal import Decimal
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .models import (
    MiscPurchaseOrder,
    MiscCompletionRecord,
    MiscVariation,
    UserAccount,
)


# ─────────────────────────────────────────────────────────────────────────────
# VIEW 1 — CEO Approves Budget Ceiling
# URL: /misc/<uuid:mpo_id>/approve-ceiling/
# Name: misc_ceo_approve
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def ceo_approve_misc_variation(request, mpo_id):
    """
    CEO or Project Director locks the budget ceiling on a MiscPurchaseOrder
    and creates the MiscVariation record for the BuildWatch dashboard.

    POST only — the approval button in misc_purchase.html POSTs here.
    """
    mpo = get_object_or_404(MiscPurchaseOrder, id=mpo_id)

    # Role guard — only CEO / PROJECT_DIRECTOR
    try:
        ua = request.user.useraccount
        allowed_roles = ['CEO', 'PROJECT_DIRECTOR', 'DIRECTOR']
        if ua.access_level.code not in allowed_roles:
            messages.error(
                request,
                'Only the CEO or Project Director can approve a Misc Variation budget.'
            )
            return redirect('misc_purchase_detail', mpo_id=mpo_id)
    except UserAccount.DoesNotExist:
        messages.error(request, 'User account not found.')
        return redirect('misc_purchase_detail', mpo_id=mpo_id)

    # Idempotency — already approved
    if mpo.ceiling_locked:
        messages.warning(
            request,
            f'{mpo.variation_ref or mpo.mpo_number} ceiling is already locked '
            f'at KES {mpo.budget_ceiling:,.2f}.'
        )
        return redirect('misc_purchase_detail', mpo_id=mpo_id)

    # Must have a scope and total before approving
    if not mpo.total_amount or mpo.total_amount <= 0:
        messages.error(
            request,
            'Cannot approve: total amount is zero. Ensure all items are priced before submission.'
        )
        return redirect('misc_purchase_detail', mpo_id=mpo_id)

    if request.method == 'POST':
        # Lock ceiling at current total_amount (set by the RO)
        mpo.budget_ceiling   = mpo.total_amount
        mpo.ceiling_locked   = True
        mpo.variation_status = 'APPROVED'
        mpo.save()

        # Create / update MiscVariation record for BuildWatch dashboard
        if mpo.infra_project:
            variation, created = MiscVariation.objects.get_or_create(
                mpo=mpo,
                defaults={
                    'project':        mpo.infra_project,
                    'ref':            mpo.variation_ref or mpo.mpo_number or '',
                    'description':    mpo.scope_description or mpo.task.description,
                    'approved_value': mpo.budget_ceiling,
                    'status':         'APPROVED',
                }
            )
            if not created:
                variation.approved_value = mpo.budget_ceiling
                variation.status = 'APPROVED'
                variation.save()

            # Warn if this pushes cumulative misc variations above 80% contingency
            if variation.contingency_pct > Decimal('80'):
                messages.warning(
                    request,
                    f'Warning: Cumulative Misc Variations for this project are now '
                    f'{variation.contingency_pct}% of the contingency budget. '
                    f'Review with the QS before releasing funds.'
                )

        messages.success(
            request,
            f'Budget ceiling of KES {mpo.budget_ceiling:,.2f} approved and locked '
            f'for {mpo.variation_ref or mpo.mpo_number}. '
            f'Finance can now release funds to the officer.'
        )
        return redirect('misc_purchase_detail', mpo_id=mpo_id)

    # GET — redirect back (approval is POST-only)
    return redirect('misc_purchase_detail', mpo_id=mpo_id)


# ─────────────────────────────────────────────────────────────────────────────
# VIEW 2 — Senior Engineer Signs Off Completed Work
# URL: /misc/<uuid:mpo_id>/completion-signoff/
# Name: misc_completion_signoff
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def misc_completion_signoff(request, mpo_id):
    """
    Senior Engineer records that the physical work has been completed,
    uploads photos and confirms actual cost from receipts.

    This is the gate before Finance can reconcile (CashClearingRecord).
    """
    mpo = get_object_or_404(MiscPurchaseOrder, id=mpo_id)

    # Must be ceiling-locked before sign-off makes sense
    if not mpo.ceiling_locked:
        messages.error(
            request,
            'CEO must approve the budget ceiling before work can be signed off.'
        )
        return redirect('misc_purchase_detail', mpo_id=mpo_id)

    # Prevent duplicate sign-off
    if hasattr(mpo, 'completion_record'):
        messages.warning(
            request,
            f'Completion record already exists for {mpo.variation_ref}. '
            f'Contact Finance to proceed with reconciliation.'
        )
        return redirect('misc_purchase_detail', mpo_id=mpo_id)

    if request.method == 'POST':
        actual_cost_raw = request.POST.get('actual_cost', '0').replace(',', '')
        try:
            actual_cost = Decimal(actual_cost_raw)
        except Exception:
            messages.error(request, 'Invalid actual cost value.')
            return redirect('misc_completion_signoff', mpo_id=mpo_id)

        photo_1 = request.FILES.get('photo_1')
        if not photo_1:
            messages.error(
                request,
                'At least one photo of the completed work is required.'
            )
            return render(request, 'misc_completion_signoff.html', {'mpo': mpo})

        try:
            ua = request.user.useraccount
        except UserAccount.DoesNotExist:
            messages.error(request, 'User account not found.')
            return redirect('misc_purchase_detail', mpo_id=mpo_id)

        record = MiscCompletionRecord(
            mpo             = mpo,
            completed_by    = ua,
            scope_achieved  = request.POST.get('scope_achieved', '').strip(),
            actual_cost     = actual_cost,
            quality_notes   = request.POST.get('quality_notes', '').strip(),
            photo_1         = photo_1,
            photo_2         = request.FILES.get('photo_2'),
            photo_3         = request.FILES.get('photo_3'),
        )
        record.save()  # auto-computes variance, advances variation_status

        # Update MiscVariation actual_value and status
        if hasattr(mpo, 'variation_record'):
            mv = mpo.variation_record
            mv.actual_value   = actual_cost
            mv.status         = 'RECONCILED'
            mv.reconciled_at  = timezone.now()
            mv.save()

        # Overspend warning
        if record.variance_amount > Decimal('0'):
            messages.warning(
                request,
                f'Work signed off. NOTE: Actual cost KES {actual_cost:,.2f} exceeds '
                f'approved ceiling by KES {record.variance_amount:,.2f}. '
                f'This variance requires CEO explanation before GL close.'
            )
        else:
            messages.success(
                request,
                f'Work signed off for {mpo.variation_ref}. '
                f'Underspend of KES {abs(record.variance_amount):,.2f}. '
                f'Finance can now reconcile.'
            )

        return redirect('misc_purchase_detail', mpo_id=mpo_id)

    # GET — render sign-off form
    return render(request, 'misc_completion_signoff.html', {'mpo': mpo})


# ─────────────────────────────────────────────────────────────────────────────
# VIEW 3 — Unified Variation Register (Type A + Type B)
# URL: /buildwatch/projects/<int:project_id>/variations/
# Name: project_variation_register
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def project_variation_register(request, project_id):
    """
    Unified variation register for a BuildWatch InfraProject.
    Shows both Type A (VariationOrder / subcontract) and
    Type B (MiscVariation / self-execute) in one table.
    """
    from buildwatch.models import InfraProject

    # Import Type A from execution app if it exists
    try:
        from execution.models import VariationOrder
        type_a = VariationOrder.objects.filter(
            project_id=project_id
        ).order_by('si_no')
    except ImportError:
        type_a = []

    project = get_object_or_404(InfraProject, pk=project_id)

    # Type B — misc self-execute variations
    type_b = MiscVariation.objects.filter(
        project=project
    ).order_by('ref')

    # Financial totals
    total_type_a = sum(
        (getattr(v, 'approved_value', None) or 0)
        for v in type_a
        if getattr(v, 'status', None) in ['APPROVED', 'ACTIVE', 'RECONCILED', 'PAID']
    )
    total_type_b = sum(
        v.approved_value
        for v in type_b
        if v.status in ['APPROVED', 'ACTIVE', 'RECONCILED']
    )
    total_variations = Decimal(str(total_type_a)) + total_type_b

    # Contingency
    try:
        contingency = project.task.budget.misc_reserve or Decimal('0')
    except Exception:
        contingency = Decimal('0')

    contingency_used_pct = (
        (total_variations / contingency * 100).quantize(Decimal('0.1'))
        if contingency else Decimal('0')
    )

    return render(request, 'variations/register.html', {
        'project':               project,
        'type_a_variations':     type_a,
        'type_b_variations':     type_b,
        'total_type_a':          total_type_a,
        'total_type_b':          total_type_b,
        'total_variations':      total_variations,
        'contingency':           contingency,
        'contingency_used_pct':  contingency_used_pct,
        'contingency_warn':      contingency_used_pct > Decimal('80'),
        'contingency_critical':  contingency_used_pct > Decimal('100'),
    })


# ─────────────────────────────────────────────────────────────────────────────
# GATE CHECK — add to existing create_cash_clearing view
# ─────────────────────────────────────────────────────────────────────────────
#
# In your existing create_cash_clearing view, add this block
# BEFORE the main form processing logic:
#
#   def create_cash_clearing(request, mpo_id):
#       mpo = get_object_or_404(MiscPurchaseOrder, id=mpo_id)
#
#       # ── BUILDWATCH GATE: completion record required before GL close ───
#       if mpo.ceiling_locked and not hasattr(mpo, 'completion_record'):
#           messages.error(
#               request,
#               f'Cannot reconcile {mpo.variation_ref or mpo.mpo_number}: '
#               f'Senior Engineer has not signed off the completed work. '
#               f'Request sign-off before reconciling.'
#           )
#           return redirect('misc_purchase_detail', mpo_id=mpo_id)
#       # ── End gate check ───────────────────────────────────────────────
#
#       # ... rest of existing logic unchanged ...
