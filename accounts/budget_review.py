"""GM ↔ CEO budget review workflow helpers."""

from decimal import Decimal

from accounts.models import BudgetReviewEvent, CEOFundRelease, ProjectBudget


def budget_review_events(budget):
    if not budget:
        return []
    return list(
        budget.review_events.select_related("created_by", "source_mpo", "source_mro")
    )


def sync_budget_review_status(budget, task):
    """Align review_status with CEO approval and fund release flags."""
    if not budget:
        return
    if CEOFundRelease.objects.filter(task=task).exists():
        budget.review_status = ProjectBudget.REVIEW_RELEASED
    elif budget.is_ceo_approved:
        budget.review_status = ProjectBudget.REVIEW_APPROVED
    budget.save(update_fields=["review_status"])


def record_budget_review_event(
    *,
    budget,
    task,
    action,
    user,
    memo_subject="",
    memo_body="",
    reason="",
    from_officer="",
    to_officer="",
    source_mpo=None,
    source_mro=None,
):
    return BudgetReviewEvent.objects.create(
        budget=budget,
        task=task,
        action=action,
        memo_subject=memo_subject[:200],
        memo_body=memo_body,
        reason=reason,
        from_officer=from_officer[:200],
        to_officer=to_officer[:200],
        source_mpo=source_mpo,
        source_mro=source_mro,
        created_by=user,
    )


def gm_can_send_ceo_budget_reminder(budget):
    """GM may nudge CEO while ad-hoc budget is not yet AIE-approved."""
    return bool(budget and not budget.is_ceo_approved)


def gm_can_submit_budget(budget):
    if not budget or budget.is_ceo_approved:
        return False
    return budget.review_status in (
        ProjectBudget.REVIEW_PROVISION,
        ProjectBudget.REVIEW_RETURNED,
    )


def adhoc_budget_ceiling(budget):
    if not budget:
        return Decimal("0")
    total = budget.total_authorized_budget or Decimal("0")
    if total > 0:
        return total
    return (
        (budget.material_total_cost or Decimal("0"))
        + (budget.labour_burden or Decimal("0"))
        + (budget.misc_reserve or Decimal("0"))
        + (budget.equipment_reserve or Decimal("0"))
    )


def ceo_can_return_budget(budget):
    return bool(
        budget
        and not budget.is_ceo_approved
        and budget.review_status == ProjectBudget.REVIEW_WITH_CEO
    )


def ceo_can_approve_budget(budget):
    if not budget or budget.is_ceo_approved:
        return False
    if budget.review_status == ProjectBudget.REVIEW_RETURNED:
        return False
    if budget.budget_type == ProjectBudget.BUDGET_ADHOC_MISC:
        if adhoc_budget_ceiling(budget) <= 0:
            return False
        return budget.review_status in (
            ProjectBudget.REVIEW_PROVISION,
            ProjectBudget.REVIEW_WITH_CEO,
        )
    return budget.review_status in (
        ProjectBudget.REVIEW_PROVISION,
        ProjectBudget.REVIEW_WITH_CEO,
    )


def budget_review_status_label(budget):
    if not budget:
        return "No provision budget"
    return dict(ProjectBudget.REVIEW_STATUS_CHOICES).get(
        budget.review_status, budget.review_status
    )
