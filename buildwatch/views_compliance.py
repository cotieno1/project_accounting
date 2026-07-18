# ============================================================================
# buildwatch/views_compliance.py
#
# Compliance & Sign-off Register for a tender's works.
#   compliance_register  GET  /tenders/<id>/compliance/
#   compliance_action    POST /tenders/<id>/compliance/action/
#
# Anchored to BOQ preamble clauses (hold points, certificates), plus site
# readiness items (storage, CCTV, equipment). Each checkpoint has a responsible
# person, evidence and a sign-off; overdue items raise missed-step alerts.
# ============================================================================
from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.models import UserAccount
from accounts.tenant import branding_template_context, get_active_organization

from .models import (
    AuditLedger,
    BidderRegistration,
    ComplianceCheckpoint,
    TenderListing,
)

CATEGORY_ORDER = [
    ComplianceCheckpoint.SITE_READINESS,
    ComplianceCheckpoint.HOLD_POINT,
    ComplianceCheckpoint.INSPECTION,
    ComplianceCheckpoint.CERTIFICATE,
]


def _current_ua(request):
    return UserAccount.objects.filter(user=request.user).select_related("organization").first()


def _name(ua):
    if not ua:
        return ""
    full = ("%s %s" % (getattr(ua, "first_name", ""), getattr(ua, "last_name", ""))).strip()
    return full or getattr(ua, "email", "") or str(ua)


def _access(request, listing):
    """Return a dict of capabilities, or None if the user may not view."""
    if not (request.user and request.user.is_authenticated):
        return None
    org = get_active_organization(request)
    owner = getattr(getattr(listing.event, "project", None), "owner_org", None)
    is_sponsor = bool(org and owner and org.pk == owner.pk)
    is_bidder = bool(
        org and BidderRegistration.objects.filter(tender=listing, organisation=org).exists()
    )
    is_admin = bool(request.user.is_superuser)
    if not (is_sponsor or is_bidder or is_admin):
        return None
    return {
        "org": org,
        "is_sponsor": is_sponsor,
        "is_bidder": is_bidder,
        "is_admin": is_admin,
        "can_approve": is_sponsor or is_admin,
        "can_submit": is_sponsor or is_bidder or is_admin,
    }


def _audit(listing, ua, action, cp, extra=None):
    try:
        AuditLedger.objects.create(
            project=getattr(listing.event, "project", None),
            user=ua,
            action=action,
            model_name="ComplianceCheckpoint",
            object_id=str(cp.pk),
            detail={"code": cp.code, "title": cp.title, "status": cp.status, **(extra or {})},
            professional_reg=getattr(ua, "professional_reg_no", "") or "",
        )
    except Exception:
        pass


def _notify(subject, to_emails, body):
    to = [e for e in (to_emails or []) if e]
    if not to:
        return
    try:
        from accounts.emails import send_system_email

        send_system_email(subject=subject, to=to, text_body=body)
    except Exception:
        pass


@login_required
def compliance_register(request, listing_id):
    listing = get_object_or_404(
        TenderListing.objects.select_related("event", "event__project", "event__project__owner_org"),
        pk=listing_id,
    )
    caps = _access(request, listing)
    if caps is None:
        messages.error(request, "You do not have access to this tender's compliance register.")
        return redirect("tender-detail", listing_id=listing.pk)

    checkpoints = list(listing.checkpoints.select_related("responsible_user", "signed_off_by"))
    today = timezone.now().date()

    groups = []
    label_map = dict(ComplianceCheckpoint.CATEGORY_CHOICES)
    present = [c for c in CATEGORY_ORDER if any(cp.category == c for cp in checkpoints)]
    for cat in present:
        items = [cp for cp in checkpoints if cp.category == cat]
        groups.append({
            "code": cat,
            "label": label_map.get(cat, cat),
            "items": items,
            "open_count": sum(1 for cp in items if cp.is_open),
        })

    approved = sum(1 for cp in checkpoints if cp.status == ComplianceCheckpoint.STATUS_APPROVED)
    submitted = sum(1 for cp in checkpoints if cp.status == ComplianceCheckpoint.STATUS_SUBMITTED)
    overdue = [cp for cp in checkpoints if cp.is_overdue]
    total = len(checkpoints)
    pct = int(round(approved * 100 / total)) if total else 0

    ctx = {
        "listing": listing,
        "caps": caps,
        "groups": groups,
        "overdue": overdue,
        "stats": {
            "total": total,
            "approved": approved,
            "submitted": submitted,
            "overdue": len(overdue),
            "open": total - approved,
            "pct": pct,
        },
        "role_choices": ComplianceCheckpoint.ROLE_CHOICES,
        "today": today,
        **branding_template_context(request),
    }
    return render(request, "tenders/compliance_register.html", ctx)


@login_required
@require_POST
def compliance_action(request, listing_id):
    listing = get_object_or_404(
        TenderListing.objects.select_related("event", "event__project", "event__project__owner_org"),
        pk=listing_id,
    )
    caps = _access(request, listing)
    if caps is None:
        messages.error(request, "You do not have access to this tender's compliance register.")
        return redirect("tender-detail", listing_id=listing.pk)

    ua = _current_ua(request)
    cp = get_object_or_404(ComplianceCheckpoint, pk=request.POST.get("checkpoint_id"), tender=listing)
    action = (request.POST.get("action") or "").strip()
    owner = getattr(listing.event, "project", None)
    owner_org = getattr(owner, "owner_org", None)
    sponsor_email = getattr(owner_org, "email", "") if owner_org else ""

    if action == "assign":
        cp.responsible_user = ua
        due = (request.POST.get("due_date") or "").strip()
        if due:
            cp.due_date = due
        note = (request.POST.get("notes") or "").strip()
        if note:
            cp.notes = note
        cp.save()
        _audit(listing, ua, "COMPLIANCE_ASSIGNED", cp,
               {"responsible": _name(ua)})
        messages.success(request, "You are now responsible for: %s" % cp.title)

    elif action == "submit":
        if not caps["can_submit"]:
            messages.error(request, "You cannot submit evidence for this checkpoint.")
            return redirect("compliance-register", listing_id=listing.pk)
        if request.FILES.get("evidence"):
            cp.evidence = request.FILES["evidence"]
        cp.certificate_ref = (request.POST.get("certificate_ref") or "").strip()[:100]
        note = (request.POST.get("notes") or "").strip()
        if note:
            cp.notes = note
        if cp.responsible_user_id is None:
            cp.responsible_user = ua
        cp.status = ComplianceCheckpoint.STATUS_SUBMITTED
        cp.submitted_at = timezone.now()
        cp.save()
        _audit(listing, ua, "COMPLIANCE_SUBMITTED", cp)
        _notify(
            "Compliance sign-off requested: %s" % cp.title,
            [sponsor_email],
            "%s has submitted evidence for '%s' (%s) on tender %s and it is awaiting "
            "your sign-off.\n\nReview: %s"
            % (
                (_name(ua) or "A contractor"),
                cp.title, cp.get_category_display(), listing.event.ref,
                request.build_absolute_uri(reverse("compliance-register", args=[listing.pk])),
            ),
        )
        messages.success(request, "Submitted for sign-off: %s" % cp.title)

    elif action in {"approve", "reject", "na"}:
        if not caps["can_approve"]:
            messages.error(request, "Only the procuring entity / approver can sign off.")
            return redirect("compliance-register", listing_id=listing.pk)
        note = (request.POST.get("notes") or "").strip()
        if note:
            cp.notes = note
        if action == "approve":
            cp.status = ComplianceCheckpoint.STATUS_APPROVED
            cp.signed_off_by = ua
            cp.signed_off_at = timezone.now()
            act = "CERT_ISSUED" if cp.category == ComplianceCheckpoint.CERTIFICATE else "COMPLIANCE_APPROVED"
            msg = "Signed off: %s" % cp.title
        elif action == "reject":
            cp.status = ComplianceCheckpoint.STATUS_REJECTED
            act = "COMPLIANCE_REJECTED"
            msg = "Sent back for rework: %s" % cp.title
        else:
            cp.status = ComplianceCheckpoint.STATUS_NA
            act = "COMPLIANCE_NA"
            msg = "Marked not applicable: %s" % cp.title
        cp.save()
        _audit(listing, ua, act, cp)
        resp_email = getattr(cp.responsible_user, "email", "") if cp.responsible_user_id else ""
        _notify(
            "Compliance %s: %s" % (cp.get_status_display(), cp.title),
            [resp_email],
            "Checkpoint '%s' on tender %s was marked %s by %s.%s"
            % (
                cp.title, listing.event.ref, cp.get_status_display(),
                (_name(ua) or "the approver"),
                ("\n\nNote: " + note) if note else "",
            ),
        )
        messages.success(request, msg)
    else:
        messages.error(request, "Unknown action.")

    return redirect("compliance-register", listing_id=listing.pk)
