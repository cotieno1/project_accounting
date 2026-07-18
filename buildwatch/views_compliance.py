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

# Construction sequence used to lay out the draft programme of works.
TRADE_SEQUENCE = {
    "EXCAVATION": 1, "CONCRETE": 2, "WALLING": 3, "STEELWORK": 3,
    "ROOFING": 4, "CARPENTRY": 5, "METALWORK": 5, "PLUMBING": 6,
    "DRAINAGE": 6, "GLAZING": 7, "FINISHINGS": 7, "PAINTING": 8,
    "PAVINGS": 8, "GENERAL": 9,
}
PHASE_LABELS = {
    0: "Mobilisation & Site Readiness",
    1: "Substructure - Excavation & Earthworks",
    2: "Concrete Works",
    3: "Walling & Structural Frame",
    4: "Roofing",
    5: "Carpentry, Joinery & Metalwork",
    6: "Plumbing & Drainage",
    7: "Finishes & Glazing",
    8: "Painting & External Works",
    9: "General & Handover",
}
CERT_HEADINGS = {
    ComplianceCheckpoint.CERTIFICATE: "Certificate of Compliance",
    ComplianceCheckpoint.HOLD_POINT: "Hold Point Release / Approval Record",
    ComplianceCheckpoint.INSPECTION: "Inspection Sign-off Record",
    ComplianceCheckpoint.SITE_READINESS: "Site Readiness Confirmation",
}


def _phase_of(cp):
    if cp.category == ComplianceCheckpoint.SITE_READINESS:
        return 0
    code = (cp.preamble.trade_code if cp.preamble_id else "") or ""
    return TRADE_SEQUENCE.get(code.upper(), 9)


def _draft_programme(checkpoints):
    """Lay checkpoints out as a draft programme of works (phases + milestones)."""
    from collections import defaultdict

    buckets = defaultdict(list)
    for cp in checkpoints:
        buckets[_phase_of(cp)].append(cp)

    phases = []
    start = 1
    for idx in sorted(buckets):
        items = buckets[idx]
        dur = max(2, min(6, len(items)))
        end = start + dur - 1
        phases.append({
            "idx": idx,
            "label": PHASE_LABELS.get(idx, "Phase %d" % idx),
            "start": start, "end": end, "duration": dur,
            "items": items, "count": len(items),
        })
        start = end + 1

    total = phases[-1]["end"] if phases else 0
    for p in phases:
        p["left_pct"] = round((p["start"] - 1) * 100.0 / total, 2) if total else 0
        p["width_pct"] = round(p["duration"] * 100.0 / total, 2) if total else 0
        p["target_week"] = p["end"]
    return {"phases": phases, "total_weeks": total,
            "end_by_phase": {p["idx"]: p["end"] for p in phases}}


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

    programme = _draft_programme(checkpoints)
    dated = [cp.due_date for cp in checkpoints if cp.due_date]
    start_default = min(dated).isoformat() if dated else today.isoformat()

    ctx = {
        "listing": listing,
        "caps": caps,
        "groups": groups,
        "programme": programme,
        "start_default": start_default,
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
    action = (request.POST.get("action") or "").strip()
    owner = getattr(listing.event, "project", None)
    owner_org = getattr(owner, "owner_org", None)
    sponsor_email = getattr(owner_org, "email", "") if owner_org else ""

    # Programme-wide action (no single checkpoint) - handle before the lookup.
    if action == "apply_programme":
        if not caps["can_submit"]:
            messages.error(request, "You cannot set the programme dates.")
            return redirect("compliance-register", listing_id=listing.pk)
        from datetime import datetime, timedelta

        raw = (request.POST.get("start_date") or "").strip()
        try:
            start = datetime.strptime(raw, "%Y-%m-%d").date()
        except ValueError:
            messages.error(request, "Enter a valid programme start date.")
            return redirect("compliance-register", listing_id=listing.pk)
        checkpoints = list(listing.checkpoints.all())
        prog = _draft_programme(checkpoints)
        updated = 0
        for c in checkpoints:
            if c.status in (ComplianceCheckpoint.STATUS_APPROVED, ComplianceCheckpoint.STATUS_NA):
                continue
            wk = prog["end_by_phase"].get(_phase_of(c), prog["total_weeks"])
            c.due_date = start + timedelta(weeks=wk)
            c.save(update_fields=["due_date"])
            updated += 1
        messages.success(request, "Draft programme applied - due dates set for %d milestones." % updated)
        return redirect("compliance-register", listing_id=listing.pk)

    cp = get_object_or_404(ComplianceCheckpoint, pk=request.POST.get("checkpoint_id"), tender=listing)

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


@login_required
def compliance_sample_certificate(request, listing_id, checkpoint_id):
    """Render a sample / template certificate (or sign-off record) for a checkpoint."""
    listing = get_object_or_404(
        TenderListing.objects.select_related("event", "event__project", "event__project__owner_org"),
        pk=listing_id,
    )
    caps = _access(request, listing)
    if caps is None:
        messages.error(request, "You do not have access to this tender's compliance register.")
        return redirect("tender-detail", listing_id=listing.pk)

    cp = get_object_or_404(ComplianceCheckpoint, pk=checkpoint_id, tender=listing)
    owner_org = getattr(getattr(listing.event, "project", None), "owner_org", None)

    ctx = {
        "listing": listing,
        "cp": cp,
        "owner_org": owner_org,
        "contractor_org": caps.get("org"),
        "heading": CERT_HEADINGS.get(cp.category, "Compliance Record"),
        "today": timezone.now().date(),
    }
    from accounts.misc_doc_pdf import build_pdf_bytes, pdf_inline_response

    pdf = build_pdf_bytes("tenders/compliance_certificate_print.html", ctx)
    ref = (listing.event.ref or "").replace("/", "-")
    return pdf_inline_response(pdf, "SAMPLE-%s-%s" % (cp.code, ref))
