# ============================================================================
# accounts/views_auth.py
#
# DOMAIN: Authentication, Users, Dashboard, Master Data API
#
# Functions from original views.py:
#   CustomLoginView          line 185
#   has_module_access        line 202
#   home                     line 216
#   health                   line 220
#   health_email             line 225
#   set_password_onboarding  line 245
#   password_change_required line 290
#   resend_onboarding_email  line 303
#   android_rollout_plan_doc line 325
#   dashboard                line 330
#   switch_active_organization line 381
#   fin_mgmt_ops_view        line 491
#   get_pioneer_model        line 510
#   _entity_* helpers        lines 633–820
#   unified_api_create       line 823
#   get_entity_list          line 914
#   get_entity_detail        line 951
#   delete_entity            line 991
#   _validate_user_passwords line 1034
#   _ensure_useraccount_login line 1048
#   _send_user_onboarding_invite line 1089
#   create_user              line 1113
#   supplier_lookup          line 1339
#   buildwatch_register      NEW
#   buildwatch_register_pending NEW
#
# ~1,400 lines
# ============================================================================

from .views_shared import *
from .emails import send_onboarding_email


# ── PASTE from views.py: lines 185–1357 ──────────────────────────────────────
# Instructions:
#   1. Open views.py
#   2. Copy lines 185 to 1357 inclusive
#   3. Paste them here, replacing this comment block
#   4. The imports at the top of this file (views_shared *) supply everything
#      those functions need — no additional import statements required
# ─────────────────────────────────────────────────────────────────────────────


# ── BuildWatch self-registration (new — not in original views.py) ─────────────

def buildwatch_register(request):
    """
    Public self-registration for BuildWatch.
    GET  → renders templates/buildwatch/register.html (4-step form)
    POST → creates Organization + UserAccount, fires onboarding email,
           redirects to buildwatch_register_pending.
    Uses same creation pattern as create_user() above.
    """
    if request.method == 'GET':
        return render(request, 'buildwatch/register.html')

    p = request.POST
    org_name        = (p.get('org_name')          or '').strip()
    org_short       = (p.get('org_short')         or '').strip()
    org_type        = (p.get('org_type')           or '').strip()
    org_country     = (p.get('org_country')        or 'KE').strip()
    org_county      = (p.get('org_county')         or '').strip()
    org_pin         = (p.get('org_pin')            or '').strip()
    org_phone       = (p.get('org_phone')          or '').strip()
    org_address     = (p.get('org_address')        or '').strip()
    first_name      = (p.get('user_first')         or '').strip()
    last_name       = (p.get('user_last')          or '').strip()
    email           = (p.get('user_email')         or '').strip()
    phone           = (p.get('user_phone')         or '').strip()
    designation     = (p.get('user_designation')   or '').strip()
    buildwatch_role = (p.get('buildwatch_role')    or '').strip()
    licence_body    = (p.get('licence_body')       or '').strip()
    licence_no      = (p.get('licence_no')         or '').strip()
    licence_expiry  = p.get('licence_expiry')      or None
    licence_class   = (p.get('licence_class')      or '').strip()
    staff_no        = (p.get('staff_no')           or '').strip()
    tos_agreed      = p.get('tos_agreed') == '1'

    errors = []
    if not org_name:        errors.append('Organisation name is required.')
    if not org_short:       errors.append('Short name is required.')
    if not org_type:        errors.append('Organisation type is required.')
    if not first_name:      errors.append('First name is required.')
    if not last_name:       errors.append('Last name is required.')
    if not email or '@' not in email:
        errors.append('A valid email address is required.')
    if not phone:           errors.append('Mobile number is required.')
    if not designation:     errors.append('Designation is required.')
    if not buildwatch_role: errors.append('Please select your role.')
    if not licence_body:    errors.append('Please select your licensing body.')
    if licence_body and licence_body != 'NONE' and not licence_no:
        errors.append('Professional registration number is required.')
    if not tos_agreed:      errors.append('You must agree to the Terms of Use.')
    if email and User.objects.filter(email=email).exists():
        errors.append(f'An account with email {email} already exists.')

    if errors:
        for e in errors:
            messages.error(request, e)
        return render(request, 'buildwatch/register.html')

    # Username — same logic as create_user()
    username = email.split('@')[0].strip() or (first_name + last_name).lower()
    base_username = username
    counter = 1
    while User.objects.filter(username=username).exists():
        username = f'{base_username}{counter}'
        counter += 1

    # Staff no
    if not staff_no:
        staff_no = f'BW-{UserAccount.objects.count() + 1:05d}'
    base_staff = staff_no
    suffix = 1
    while UserAccount.objects.filter(staff_no=staff_no).exists():
        staff_no = f'{base_staff}-{suffix}'
        suffix += 1

    # Organisation
    org_code = re.sub(r'[^A-Z0-9]', '', org_short.upper())[:28] or 'ORG'
    base_code = org_code
    sfx = 1
    while Organization.objects.filter(org_code=org_code).exists():
        org_code = f'{base_code}{sfx}'
        sfx += 1

    location_tag = ', '.join(filter(None, [org_county, org_country]))

    try:
        org = Organization.objects.create(
            org_code=org_code, name=org_name, short_name=org_short,
            contact_address=location_tag, registered_address=org_address,
            phone=org_phone, email=email, tax_pin=org_pin,
            organization_type=org_type,
            document_tagline=f'{org_type} — {location_tag}',
            registration_status=Organization.STATUS_PENDING,
            is_default=False,
        )
    except Exception as exc:
        messages.error(request, f'Could not create organisation: {exc}')
        return render(request, 'buildwatch/register.html')

    ROLE_TO_CATEGORY = {
        'QS': 'QUANTITY_SURVEYOR', 'ENGINEER': 'CONSULTING_ENGINEER',
        'INSPECTOR': 'SENIOR_SITE_MANAGER', 'CLIENT': 'PROJECT_DIRECTOR',
        'CONTRACTOR': 'CONTRACTOR', 'FINANCE': 'FINANCE_OFFICER',
    }
    access_level = (
        UserCategory.objects.filter(code=ROLE_TO_CATEGORY.get(buildwatch_role, 'CONTRACTOR')).first()
        or UserCategory.objects.order_by('rank').first()
    )

    try:
        user = User.objects.create_user(
            username=username, email=email,
            password=secrets.token_urlsafe(32),
            first_name=first_name, last_name=last_name,
        )
        user.set_unusable_password()
        user.save()
    except Exception as exc:
        org.delete()
        messages.error(request, f'Could not create login: {exc}')
        return render(request, 'buildwatch/register.html')

    try:
        ua = UserAccount.objects.create(
            user=user, staff_no=staff_no,
            first_name=first_name, last_name=last_name,
            designation=designation, phone=phone, email=email,
            contact_address=location_tag,
            access_level=access_level, organization=org,
            must_change_password=True,
            registration_pending_review=True,
            professional_reg_no=licence_no,
            licence_body=licence_body,
            licence_expiry=licence_expiry or None,
            licence_class=licence_class,
            buildwatch_role=buildwatch_role,
        )
    except Exception as exc:
        user.delete()
        org.delete()
        messages.error(request, f'Could not create user account: {exc}')
        return render(request, 'buildwatch/register.html')

    try:
        ok, err = send_onboarding_email(ua, request=request, invited_by=None)
        if not ok:
            messages.warning(request,
                f'Registration received but activation email failed ({err}). '
                f'Contact support@buildwatch.co.ke.')
    except Exception as exc:
        messages.warning(request, f'Account created — email error: {exc}')

    request.session.update({
        'bw_reg_name':  f'{first_name} {last_name}',
        'bw_reg_email': email,
        'bw_reg_org':   org_name,
        'bw_reg_role':  buildwatch_role,
        'bw_reg_staff': staff_no,
    })
    return redirect('buildwatch-register-pending')


def buildwatch_register_pending(request):
    ROLE_LABELS = {
        'QS': 'Quantity Surveyor', 'ENGINEER': 'Consulting Engineer',
        'INSPECTOR': 'Site Inspector / Clerk of Works',
        'CLIENT': 'Client Representative', 'CONTRACTOR': 'Contractor',
        'FINANCE': 'Finance / Accounts',
    }
    role_code = request.session.get('bw_reg_role', '')
    return render(request, 'buildwatch/register_pending.html', {
        'name':     request.session.get('bw_reg_name',  'Applicant'),
        'email':    request.session.get('bw_reg_email', ''),
        'org':      request.session.get('bw_reg_org',   ''),
        'role':     ROLE_LABELS.get(role_code, role_code),
        'staff_no': request.session.get('bw_reg_staff', ''),
    })
