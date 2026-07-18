# ============================================================================
# buildwatch/delivery.py
#
# Project Delivery Hub logic: value-for-money rollup (contract sum vs certified
# vs paid vs retention held) and recording the award / contract sum.
#
# The money spine that proves "every shilling is accounted for and what was
# promised was delivered". Payment certificates are summed incrementally.
# ============================================================================
from __future__ import annotations

from decimal import Decimal

from django.utils import timezone

from .models import AuditLedger, PaymentCertificate

Z = Decimal("0")


def _q(v):
    return (v or Z).quantize(Decimal("0.01"))


def value_for_money(project):
    """Return the contract-sum -> certified -> paid -> retention rollup for a project."""
    contract_sum = project.contract_value or Z

    certs = list(project.payment_certificates.all())
    live = [c for c in certs if c.status != PaymentCertificate.STATUS_DRAFT]

    def _sum(items, attr):
        return sum((getattr(c, attr) or Z for c in items), Z)

    contractor = [c for c in live if c.payee_kind == PaymentCertificate.CONTRACTOR]
    consultant = [c for c in live if c.payee_kind == PaymentCertificate.CONSULTANT]
    paid = [c for c in live if c.status == PaymentCertificate.STATUS_PAID]

    certified_gross = _sum(live, "gross_amount")
    certified_net = _sum(live, "net_payable")
    retention_held = _sum(live, "retention_amount") - _sum(live, "retention_released")
    paid_to_date = _sum(paid, "net_payable")
    outstanding = certified_net - paid_to_date
    balance = contract_sum - certified_gross

    def _pct(part, whole):
        if not whole:
            return 0
        return max(0, min(100, int(round(float(part) * 100.0 / float(whole)))))

    budget = None
    try:
        from accounts.models import ProjectBudget

        pb = ProjectBudget.objects.filter(task=project.task).first()
        if pb:
            budget = pb.total_authorized_budget
    except Exception:
        budget = None

    return {
        "contract_sum": _q(contract_sum),
        "budget": _q(budget) if budget is not None else None,
        "certified_gross": _q(certified_gross),
        "certified_net": _q(certified_net),
        "retention_held": _q(retention_held),
        "paid_to_date": _q(paid_to_date),
        "outstanding": _q(outstanding),
        "balance": _q(balance),
        "contractor_paid": _q(_sum([c for c in paid if c.payee_kind == PaymentCertificate.CONTRACTOR], "net_payable")),
        "consultant_paid": _q(_sum([c for c in paid if c.payee_kind == PaymentCertificate.CONSULTANT], "net_payable")),
        "contractor_certs": len(contractor),
        "consultant_certs": len(consultant),
        "cert_count": len(live),
        "draft_count": sum(1 for c in certs if c.status == PaymentCertificate.STATUS_DRAFT),
        "pct_certified": _pct(certified_gross, contract_sum),
        "pct_paid": _pct(paid_to_date, contract_sum),
        "pct_certified_only": max(0, _pct(certified_gross, contract_sum) - _pct(paid_to_date, contract_sum)),
        "over_budget": bool(budget is not None and certified_gross > budget),
    }


def record_award(tender, org, amount, ua):
    """Record the award: set the project contract sum and mark the winning bid.

    Returns the InfraProject that was updated (or None).
    """
    project = getattr(getattr(tender, "event", None), "project", None)
    if project is None:
        return None

    amount = _q(amount)
    project.contract_value = amount
    project.save(update_fields=["contract_value"])

    # If the awarded org submitted a bid against this tender, flag it.
    try:
        from .models import EvaluationEvent, Submission

        sub = (
            Submission.objects
            .filter(event=tender.event, submitter_org=org)
            .first()
        )
        if sub:
            sub.is_awarded = True
            sub.rank = sub.rank or 1
            sub.save(update_fields=["is_awarded", "rank"])
            ev = tender.event
            if hasattr(EvaluationEvent, "STATUS_AWARDED"):
                ev.status = EvaluationEvent.STATUS_AWARDED
            else:
                ev.status = "AWARDED"
            ev.save(update_fields=["status"])
    except Exception:
        pass

    try:
        AuditLedger.objects.create(
            project=project,
            user=ua,
            action="TENDER_AWARDED",
            model_name="InfraProject",
            object_id=str(project.pk),
            detail={
                "tender": getattr(tender.event, "ref", ""),
                "awarded_to": getattr(org, "name", ""),
                "contract_sum": str(amount),
            },
            professional_reg=getattr(ua, "professional_reg_no", "") or "",
        )
    except Exception:
        pass

    return project
