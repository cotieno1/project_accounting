"""
Resolve / create contractor organisations used as domestic or nominated subs.

A BuildWatch contractor org (contractor ID = org_code) can act as:
- main contractor on one tender / project, and
- sub-contractor on another — the org ID outlives a single tender.
"""

from __future__ import annotations

import re
import secrets


def _org_code_from_name(company_name: str, preferred: str = "") -> str:
    if preferred:
        code = re.sub(r"[^A-Za-z0-9]+", "", preferred.upper())[:30]
        if code:
            return code
    cleaned = re.sub(r"[^A-Za-z0-9]+", " ", (company_name or "").upper()).strip()
    skip = {
        "SYSTEM", "SYSTEMS", "TECHNOLOGIES", "TECHNOLOGY", "LTD", "LIMITED",
        "CO", "COMPANY", "THE", "AND",
    }
    parts = [p for p in cleaned.split() if p and p not in skip]
    if not parts:
        parts = [p for p in cleaned.split() if p][:2]
    code = "".join(parts[:2])[:30] if parts else "SUBCO"
    return code or "SUBCO"


def ensure_contractor_organisation(
    *,
    company_name: str,
    email: str = "",
    phone: str = "",
    org_code: str = "",
):
    """
    Find or create an ACTIVE BUILDING contractor org for the named firm.
    Returns (organization, created).
    """
    from accounts.models import Organization

    name = (company_name or "").strip() or "Sub-contractor"
    short = name.split("—")[0].split("-")[0].strip()
    if len(short) > 80:
        short = short[:80]
    upper = name.upper().replace(" ", "")
    if "LANBASE" in upper:
        code = "LANBASE"
        short = "LANBase"
        name = "LANBase System Technologies"
    else:
        code = _org_code_from_name(name, preferred=org_code)

    org = Organization.objects.filter(org_code__iexact=code).first()
    if org is None and email:
        org = Organization.objects.filter(email__iexact=email.strip()).first()
    if org is None:
        base = code
        n = 2
        while Organization.objects.filter(org_code=code).exists():
            code = f"{base}{n}"[:30]
            n += 1
        org = Organization.objects.create(
            org_code=code,
            name=name[:200],
            short_name=short[:80] or code,
            email=(email or "").strip()[:254],
            phone=(phone or "").strip()[:30],
            contractor_type=Organization.CONTRACTOR_BUILDING,
            organization_type="CONTRACTOR",
            registration_status=Organization.STATUS_ACTIVE,
            document_tagline="Subcontractor Operations",
        )
        return org, True

    changed = []
    if (org.organization_type or "").upper() != "CONTRACTOR":
        org.organization_type = "CONTRACTOR"
        changed.append("organization_type")
    if org.registration_status != Organization.STATUS_ACTIVE:
        org.registration_status = Organization.STATUS_ACTIVE
        changed.append("registration_status")
    if email and not org.email:
        org.email = email.strip()[:254]
        changed.append("email")
    if phone and not org.phone:
        org.phone = phone.strip()[:30]
        changed.append("phone")
    if code == "LANBASE":
        if org.short_name != "LANBase":
            org.short_name = "LANBase"
            changed.append("short_name")
        if org.name != "LANBase System Technologies":
            org.name = "LANBase System Technologies"
            changed.append("name")
    if changed:
        org.save(update_fields=list(dict.fromkeys(changed)))
    return org, False


def ensure_subcontractor_employee(
    *,
    organization,
    email: str,
    first_name: str = "",
    last_name: str = "",
    contact_name: str = "",
    phone: str = "",
    staff_no: str = "",
    username: str = "",
):
    """
    Ensure a UserAccount (and Django login) under the contractor org.
    Creates a dedicated employee login for the sub firm (does not reassign
    an existing platform/main admin UserAccount to the sub org).
    Returns (user_account, created).
    """
    from django.contrib.auth import get_user_model

    from accounts.models import UserAccount, UserCategory
    from accounts.roles import REGULAR_USER

    User = get_user_model()
    email = (email or "").strip().lower()
    if not email or "@" not in email:
        raise ValueError("A valid employee email is required.")

    if contact_name and not (first_name or last_name):
        bits = contact_name.strip().split()
        first_name = bits[0] if bits else "Sub"
        last_name = " ".join(bits[1:]) if len(bits) > 1 else "Contractor"

    first_name = (first_name or "Sub").strip()[:100]
    last_name = (last_name or "Contractor").strip()[:100]
    phone = (phone or "0700000000").strip()[:20] or "0700000000"

    def _link_login(ua, uname):
        if ua.user_id:
            user = ua.user
            if User.objects.filter(username=uname).exclude(pk=user.pk).exists():
                uname = f"{uname}-{ua.staff_no[-4:]}"[:150]
            user.username = uname
            user.email = email
            user.first_name = first_name
            user.last_name = last_name
            user.save()
            return user
        if User.objects.filter(username=uname).exists():
            uname = f"{uname}-{organization.org_code.lower()}"[:150]
        user = User.objects.create_user(
            username=uname,
            email=email,
            password=secrets.token_urlsafe(24),
            first_name=first_name,
            last_name=last_name,
        )
        user.set_unusable_password()
        user.save()
        ua.user = user
        ua.must_change_password = True
        ua.save(update_fields=["user", "must_change_password"])
        return user

    ua = UserAccount.objects.filter(
        organization=organization, email__iexact=email
    ).first()
    created = False
    if ua is None:
        code = organization.org_code.upper()
        staff = (staff_no or f"{code[:8]}-01").strip()[:20]
        n = 1
        while UserAccount.objects.filter(staff_no=staff).exists():
            n += 1
            staff = f"{code[:6]}-{n:02d}"[:20]
        uname = (username or f"{code.lower()}.user").strip()[:150]
        role = UserCategory.objects.filter(code=REGULAR_USER).first()
        ua = UserAccount.objects.create(
            staff_no=staff,
            first_name=first_name,
            last_name=last_name,
            designation="Sub-contractor estimator",
            contact_address=organization.name,
            phone=phone,
            email=email,
            access_level=role,
            organization=organization,
            must_change_password=True,
            buildwatch_role="CONTRACTOR",
            registration_pending_review=False,
        )
        created = True
        _link_login(ua, uname)
    else:
        uname = (
            username
            or (ua.user.username if ua.user_id else f"{organization.org_code.lower()}.user")
        ).strip()[:150]
        _link_login(ua, uname)
    return ua, created


def link_arrangement_to_contractor(arrangement, organization):
    """Attach contractor org to arrangement for the life of this tender/project bid."""
    fields = []
    if arrangement.sub_organisation_id != organization.org_code:
        arrangement.sub_organisation = organization
        fields.append("sub_organisation")
    if organization.name and arrangement.sub_company_name != organization.name:
        arrangement.sub_company_name = organization.name[:200]
        fields.append("sub_company_name")
    if fields:
        fields.append("updated_at")
        arrangement.save(update_fields=fields)
    return arrangement
