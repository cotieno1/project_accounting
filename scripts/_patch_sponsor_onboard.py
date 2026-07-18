from pathlib import Path

# --- views.py constants and home/register ---
vp = Path("accounts/views.py")
vt = vp.read_text(encoding="utf-8")

if "BUILDWATCH_SPONSOR_TYPES" not in vt:
    vt = vt.replace(
        '''BUILDWATCH_CONSULTANT_DISCIPLINES = [
    ("QS", "Quantity surveyor (QS)"),
    ("ARCHITECT", "Architect"),
    ("STRUCTURAL", "Structural engineer"),
    ("CIVIL", "Civil engineer"),
    ("MEP", "MEP consultant"),
    ("PM", "Project / contract manager"),
]
''',
        '''BUILDWATCH_CONSULTANT_DISCIPLINES = [
    ("QS", "Quantity surveyor (QS)"),
    ("ARCHITECT", "Architect"),
    ("STRUCTURAL", "Structural engineer"),
    ("CIVIL", "Civil engineer"),
    ("MEP", "MEP consultant"),
    ("PM", "Project / contract manager"),
]

BUILDWATCH_SPONSOR_TYPES = [
    ("GOV_NATIONAL", "National government — ministry / department / agency"),
    ("GOV_COUNTY", "County government"),
    ("PARASTATAL", "Parastatal / state corporation"),
    ("FINANCIER", "Development financier (World Bank, AfDB, IFC, etc.)"),
    ("DEVELOPER", "Private developer / PPP consortium (local or international)"),
    ("PRIVATE", "Private company / corporate project owner"),
    ("NGO", "NGO / international development partner"),
    ("INSTITUTION", "Institution (university, hospital, faith-based)"),
    ("CLIENT", "Other project client / employer / sponsor"),
]

BUILDWATCH_PROJECT_SECTORS = [
    ("BUILDINGS", "Buildings"),
    ("ROADS", "Roads & bridges"),
    ("WATER", "Water & sanitation"),
    ("ENERGY", "Energy"),
    ("ICT", "ICT infrastructure"),
    ("OTHER", "Other"),
]

BUILDWATCH_PROJECT_TYPES = [
    ("GOV", "Government"),
    ("PPP", "Public-Private Partnership"),
    ("PRIVATE", "Private"),
]
'''
    )
    print("sponsor constants added")
else:
    print("sponsor constants exist")

# home context
old_home = '''            "contractor_categories": BUILDWATCH_CONTRACTOR_CATEGORIES,
            "consultant_disciplines": BUILDWATCH_CONSULTANT_DISCIPLINES,
            "tenant_count": tenant_count,
'''
new_home = '''            "contractor_categories": BUILDWATCH_CONTRACTOR_CATEGORIES,
            "consultant_disciplines": BUILDWATCH_CONSULTANT_DISCIPLINES,
            "sponsor_types": BUILDWATCH_SPONSOR_TYPES,
            "tenant_count": tenant_count,
'''
if "sponsor_types" not in vt:
    if old_home not in vt:
        raise SystemExit("home ctx missing")
    vt = vt.replace(old_home, new_home, 1)
    print("home ctx updated")

# register context
old_ctx = '''        "contractor_categories": BUILDWATCH_CONTRACTOR_CATEGORIES,
        "consultant_disciplines": BUILDWATCH_CONSULTANT_DISCIPLINES,
    }
'''
new_ctx = '''        "contractor_categories": BUILDWATCH_CONTRACTOR_CATEGORIES,
        "consultant_disciplines": BUILDWATCH_CONSULTANT_DISCIPLINES,
        "sponsor_types": BUILDWATCH_SPONSOR_TYPES,
        "project_sectors": BUILDWATCH_PROJECT_SECTORS,
        "project_types": BUILDWATCH_PROJECT_TYPES,
    }
'''
if "project_sectors" not in vt:
    if old_ctx not in vt:
        raise SystemExit("register ctx missing")
    vt = vt.replace(old_ctx, new_ctx, 1)
    print("register ctx updated")

# GET prefill for sponsor track
old_get = '''        elif track == "CONSULTANT" or discipline or reg_type == "CONSULTANT":
            post["org_type"] = "CONSULTANT"
            if discipline:
                post["consultant_discipline"] = discipline
        elif reg_type in ("BUILDING", "CONTRACTOR"):
'''
new_get = '''        elif track == "CONSULTANT" or discipline or reg_type == "CONSULTANT":
            post["org_type"] = "CONSULTANT"
            if discipline:
                post["consultant_discipline"] = discipline
        elif track == "SPONSOR":
            sponsor = (request.GET.get("sponsor_type") or "").strip().upper()
            if sponsor in {c for c, _ in BUILDWATCH_SPONSOR_TYPES}:
                post["org_type"] = sponsor
            else:
                post["org_type"] = "GOV_NATIONAL"
            post["registration_track"] = "SPONSOR"
        elif reg_type in ("BUILDING", "CONTRACTOR"):
'''
if 'track == "SPONSOR"' not in vt and "track == 'SPONSOR'" not in vt:
    if old_get not in vt:
        raise SystemExit("GET prefill missing")
    vt = vt.replace(old_get, new_get, 1)
    print("GET sponsor prefill added")

# Also allow INSTITUTION CLIENT in reg_type list
vt = vt.replace(
'''        elif reg_type in (
            "GOV_NATIONAL",
            "GOV_COUNTY",
            "PARASTATAL",
            "FINANCIER",
            "DEVELOPER",
            "NGO",
            "CLIENT",
            "INSTITUTION",
            "PRIVATE",
            "INDIVIDUAL",
        ):
            post["org_type"] = reg_type
''',
'''        elif reg_type in {c for c, _ in BUILDWATCH_SPONSOR_TYPES} | {"INDIVIDUAL"}:
            post["org_type"] = reg_type
            post["registration_track"] = "SPONSOR"
'''
)

# Validate sponsor + project fields; relax licence for employers
old_err = '''    if not buildwatch_role:
        errors.append("Please select your role.")
    if not licence_body:
        errors.append("Please select your licensing body.")
    if tos_agreed != "1":
'''
new_err = '''    if not buildwatch_role:
        errors.append("Please select your role.")
    sponsor_types = {c for c, _ in BUILDWATCH_SPONSOR_TYPES}
    is_sponsor = org_type in sponsor_types
    project_name = (p.get("project_name") or "").strip()
    project_code = (p.get("project_code") or "").strip().upper()
    project_sector = (p.get("project_sector") or "").strip().upper()
    project_type = (p.get("project_type") or "").strip().upper()
    project_county = (p.get("project_county") or "").strip()
    project_value_raw = (p.get("project_value") or "").strip().replace(",", "")
    if is_sponsor:
        if not project_name:
            errors.append("Project name is required for project owner / sponsor registration.")
        if not project_sector:
            errors.append("Please select the project sector.")
        if not project_type:
            errors.append("Please select the project funding type (Government / PPP / Private).")
        if not licence_body:
            licence_body = "INSTITUTIONAL"
        if not licence_no:
            licence_no = org_pin or project_code or "PENDING"
    elif not licence_body:
        errors.append("Please select your licensing body.")
    if tos_agreed != "1":
'''
if "is_sponsor = org_type in sponsor_types" not in vt:
    if old_err not in vt:
        raise SystemExit("error block missing")
    vt = vt.replace(old_err, new_err, 1)
    print("validation updated")

# After account create, create project for sponsors
old_sess = '''    request.session["bw_reg_name"] = f"{user_first} {user_last}"
    request.session["bw_reg_email"] = user_email
    request.session["bw_reg_org"] = org.name
    request.session["bw_reg_role"] = buildwatch_role
    request.session["bw_reg_staff_no"] = staff_no
    request.session["bw_reg_auto_activated"] = auto_activate_user and invite_sent
    request.session["bw_reg_org_created"] = org_created
    request.session["bw_reg_invite_error"] = invite_error

    return redirect("buildwatch-register-pending")
'''
new_sess = '''    project_created_id = ""
    if is_sponsor and project_name and org_created:
        from decimal import Decimal, InvalidOperation
        from buildwatch.models import Country, InfraProject
        from accounts.models import ProjectTask

        code = re.sub(r"[^A-Z0-9_-]", "", (project_code or project_name).upper())[:40]
        if not code:
            code = "PRJ"
        base = code
        n = 1
        while ProjectTask.objects.filter(project_id=base).exists():
            base = f"{code[:36]}-{n}"
            n += 1
        task = ProjectTask.objects.create(
            project_id=base,
            description=project_name[:200],
        )
        try:
            value = Decimal(project_value_raw) if project_value_raw else Decimal("0")
        except (InvalidOperation, ValueError):
            value = Decimal("0")
        country = Country.objects.filter(code__iexact=org_country).first()
        if country is None:
            country = Country.objects.filter(code__iexact="KE").first()
        ptype = project_type if project_type in {"GOV", "PPP", "PRIVATE"} else "GOV"
        sector = project_sector if project_sector in {c for c, _ in BUILDWATCH_PROJECT_SECTORS} else "OTHER"
        InfraProject.objects.create(
            task=task,
            owner_org=org,
            country=country,
            sector=sector,
            project_type=ptype,
            county=project_county or org_county,
            contract_value=value,
            is_active=True,
        )
        project_created_id = task.project_id

    request.session["bw_reg_name"] = f"{user_first} {user_last}"
    request.session["bw_reg_email"] = user_email
    request.session["bw_reg_org"] = org.name
    request.session["bw_reg_role"] = buildwatch_role
    request.session["bw_reg_staff_no"] = staff_no
    request.session["bw_reg_auto_activated"] = auto_activate_user and invite_sent
    request.session["bw_reg_org_created"] = org_created
    request.session["bw_reg_invite_error"] = invite_error
    request.session["bw_reg_project_id"] = project_created_id
    request.session["bw_reg_project_name"] = project_name if is_sponsor else ""

    return redirect("buildwatch-register-pending")
'''
if "bw_reg_project_id" not in vt:
    if old_sess not in vt:
        raise SystemExit("session block missing")
    vt = vt.replace(old_sess, new_sess, 1)
    print("project create added")

# pending context
old_pending = '''def buildwatch_register_pending(request):
    """Post-registration page — pending review or activation email sent."""
    context = {
        "name": request.session.get("bw_reg_name", "Applicant"),
        "email": request.session.get("bw_reg_email", ""),
'''
# find and add project fields to context
if "bw_reg_project_id" in vt and '"project_id": request.session.get("bw_reg_project_id"' not in vt:
    # locate return render pending
    marker = 'return render(request, "buildwatch_register_pending.html", context)'
    # insert before return in that function - simpler replace context dict end
    pend = '''        "invite_error": request.session.get("bw_reg_invite_error", ""),
'''
    # read around pending
    if '"project_id"' not in vt[vt.find("def buildwatch_register_pending"):vt.find("def buildwatch_register_pending")+800]:
        vt = vt.replace(
            'def buildwatch_register_pending(request):\n    """Post-registration page — pending review or activation email sent."""\n    context = {\n        "name": request.session.get("bw_reg_name", "Applicant"),\n        "email": request.session.get("bw_reg_email", ""),\n',
            'def buildwatch_register_pending(request):\n    """Post-registration page — pending review or activation email sent."""\n    context = {\n        "name": request.session.get("bw_reg_name", "Applicant"),\n        "email": request.session.get("bw_reg_email", ""),\n        "project_id": request.session.get("bw_reg_project_id", ""),\n        "project_name": request.session.get("bw_reg_project_name", ""),\n',
            1,
        )
        print("pending ctx updated")

vp.write_text(vt, encoding="utf-8")
compile(vt, "views.py", "exec")
print("views compile ok")
