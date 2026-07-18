# ============================================================================
# buildwatch/views_delivery.py
#
# Project Delivery Hub actions for a tender/project:
#   delivery_action           POST /tenders/<id>/delivery/action/
#   payment_certificate_pdf   GET  /tenders/<id>/delivery/certificate/<cid>.pdf
#
# Records the award (contract sum), raises interim/advance/final payment
# certificates to the contractor and consultants, certifies them for payment
# and marks them paid - the money spine of "every shilling accounted for".
# ============================================================================
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.models import Organization

from .delivery import record_award, value_for_money
from .models import (
    AuditLedger,
    PaymentCertificate,
    TenderConsultant,
    TenderListing,
)
from .views_compliance import _access, _current_ua, _name


def _dec(raw, default="0"):
    try:
        return Decimal(str(raw).replace(",", "").strip() or default)
    except (InvalidOperation, ValueError, AttributeError):
        return Decimal(default)


def _audit_cert(project, ua, action, cert, extra=None):
    try:
        AuditLedger.objects.create(
            project=project,
            user=ua,
            action=action,
            model_name="PaymentCertificate",
            object_id=str(cert.pk),
            detail={
                "cert_no": cert.cert_no,
                "payee": cert.payee_name,
                "net_payable": str(cert.net_payable),
                "status": cert.status,
                **(extra or {}),
            },
            professional_reg=getattr(ua, "professional_reg_no", "") or "",
        )
    except Exception:
        pass


@login_required
@require_POST
def delivery_action(request, listing_id):
    listing = get_object_or_404(
        TenderListing.objects.select_related(
            "event", "event__project", "event__project__owner_org"
        ),
        pk=listing_id,
    )
    caps = _access(request, listing)
    if caps is None or not caps["can_approve"]:
        messages.error(request, "Only the procuring entity can manage the delivery hub.")
        return redirect("tender-detail", listing_id=listing.pk)

    project = getattr(listing.event, "project", None)
    if project is None:
        messages.error(request, "This tender is not linked to a project.")
        return redirect("my-bids")

    ua = _current_ua(request)
    action = (request.POST.get("action") or "").strip()

    if action == "record_award":
        org_code = (request.POST.get("awarded_org") or "").strip()
        amount = _dec(request.POST.get("contract_sum"))
        org = Organization.objects.filter(org_code=org_code).first()
        if not org:
            messages.error(request, "Choose the awarded contractor.")
        elif amount <= 0:
            messages.error(request, "Enter the awarded contract sum.")
        else:
            record_award(listing, org, amount, ua)
            messages.success(
                request,
                "Award recorded: %s at contract sum %s." % (org.name, f"{amount:,.2f}"),
            )
        return redirect("my-bids")

    if action == "add_certificate":
        kind = (request.POST.get("payee_kind") or PaymentCertificate.CONTRACTOR).strip()
        payee_org = None
        consultant = None
        payee_name = ""
        if kind == PaymentCertificate.CONSULTANT:
            consultant = TenderConsultant.objects.filter(
                pk=request.POST.get("consultant_id"), tender=listing
            ).first()
            if consultant:
                payee_name = consultant.display_name
                payee_org = consultant.organisation
        else:
            payee_org = Organization.objects.filter(
                org_code=(request.POST.get("payee_org") or "").strip()
            ).first()
            payee_name = payee_org.name if payee_org else ""

        gross = _dec(request.POST.get("gross_amount"))
        if gross <= 0 and _dec(request.POST.get("retention_released")) <= 0:
            messages.error(request, "Enter the amount for this certificate.")
            return redirect("my-bids")

        cert = PaymentCertificate(
            project=project,
            tender=listing,
            payee_kind=kind,
            payee_org=payee_org,
            consultant=consultant,
            payee_name=payee_name[:200],
            cert_type=(request.POST.get("cert_type") or PaymentCertificate.INTERIM).strip(),
            title=(request.POST.get("title") or "").strip()[:200],
            gross_amount=gross,
            retention_pct=_dec(request.POST.get("retention_pct"), "10"),
            retention_released=_dec(request.POST.get("retention_released")),
            notes=(request.POST.get("notes") or "").strip(),
            created_by=ua,
        )
        pf = (request.POST.get("period_from") or "").strip()
        pt = (request.POST.get("period_to") or "").strip()
        if pf:
            cert.period_from = pf
        if pt:
            cert.period_to = pt
        cert.save()
        _audit_cert(project, ua, "PAYMENT_CERT_RAISED", cert)
        messages.success(
            request,
            "Draft certificate %s raised for %s (net %s)."
            % (cert.cert_no, cert.payee_name or "payee", f"{cert.net_payable:,.2f}"),
        )
        return redirect("my-bids")

    # Actions that target one certificate.
    cert = get_object_or_404(
        PaymentCertificate, pk=request.POST.get("cert_id"), project=project
    )

    if action == "certify_certificate":
        if cert.status != PaymentCertificate.STATUS_DRAFT:
            messages.error(request, "Only a draft certificate can be certified.")
            return redirect("my-bids")
        cert.status = PaymentCertificate.STATUS_CERTIFIED
        cert.certified_by = ua
        cert.certified_at = timezone.now()
        cert.save(update_fields=["status", "certified_by", "certified_at", "updated_at"])
        _audit_cert(project, ua, "PAYMENT_CERT_CERTIFIED", cert)
        messages.success(request, "Certified for payment: %s (%s)." % (cert.cert_no, f"{cert.net_payable:,.2f}"))

    elif action == "raise_ro":
        # Step 2 - raise the Requisition Order against a certified certificate.
        if cert.status != PaymentCertificate.STATUS_CERTIFIED:
            messages.error(request, "A certificate must be certified before a requisition order is raised.")
            return redirect("my-bids")
        ref = (request.POST.get("ro_no") or "").strip()[:40]
        cert.ro_no = ref or PaymentCertificate._make_seq_no("RO", "ro_no")
        cert.ro_raised_by = ua
        cert.ro_raised_at = timezone.now()
        cert.status = PaymentCertificate.STATUS_REQUISITIONED
        cert.save(update_fields=["ro_no", "ro_raised_by", "ro_raised_at", "status", "updated_at"])
        _audit_cert(project, ua, "PAYMENT_RO_RAISED", cert, {"ro_no": cert.ro_no})
        messages.success(request, "Requisition order %s raised for %s." % (cert.ro_no, cert.cert_no))

    elif action in ("raise_payment_order", "mark_paid"):
        # Step 3 - raise the Payment Order (PV) / transfer of funds.
        if cert.status != PaymentCertificate.STATUS_REQUISITIONED:
            messages.error(request, "Raise the requisition order (RO) before the payment order.")
            return redirect("my-bids")
        ref = (request.POST.get("pv_no") or "").strip()[:40]
        cert.pv_no = ref or PaymentCertificate._make_seq_no("PV", "pv_no")
        cert.paid_reference = (request.POST.get("paid_reference") or "").strip()[:100]
        cert.paid_method = (request.POST.get("paid_method") or "").strip()[:20]
        cert.paid_at = timezone.now()
        cert.status = PaymentCertificate.STATUS_PAID
        cert.save(update_fields=[
            "pv_no", "paid_reference", "paid_method", "paid_at", "status", "updated_at",
        ])
        _audit_cert(project, ua, "PAYMENT_ORDER_RAISED", cert,
                    {"pv_no": cert.pv_no, "ro_no": cert.ro_no, "reference": cert.paid_reference})
        messages.success(request, "Payment order %s raised - funds transferred for %s." % (cert.pv_no, cert.cert_no))

    elif action == "delete_certificate":
        if cert.status != PaymentCertificate.STATUS_DRAFT:
            messages.error(request, "Only draft certificates can be removed.")
        else:
            no = cert.cert_no
            cert.delete()
            messages.success(request, "Draft certificate %s removed." % no)

    else:
        messages.error(request, "Unknown action.")

    return redirect("my-bids")


@login_required
def payment_certificate_pdf(request, listing_id, cert_id):
    listing = get_object_or_404(
        TenderListing.objects.select_related(
            "event", "event__project", "event__project__owner_org"
        ),
        pk=listing_id,
    )
    caps = _access(request, listing)
    if caps is None:
        messages.error(request, "You do not have access to this project's certificates.")
        return redirect("tender-detail", listing_id=listing.pk)

    project = getattr(listing.event, "project", None)
    cert = get_object_or_404(PaymentCertificate, pk=cert_id, project=project)
    owner_org = getattr(project, "owner_org", None)

    ctx = {
        "listing": listing,
        "project": project,
        "cert": cert,
        "owner_org": owner_org,
        "vfm": value_for_money(project),
        "today": timezone.now().date(),
        "certified_by_name": _name(cert.certified_by) if cert.certified_by_id else "",
    }
    from accounts.misc_doc_pdf import build_pdf_bytes, pdf_inline_response

    pdf = build_pdf_bytes("tenders/payment_certificate_print.html", ctx)
    ref = (cert.cert_no or "certificate").replace("/", "-")
    return pdf_inline_response(pdf, ref)
