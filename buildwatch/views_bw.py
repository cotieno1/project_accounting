# ============================================================================
# buildwatch/views_bw.py
#
# DOMAIN: BuildWatch — Infrastructure Integrity Platform
# URL prefix: /buildwatch/
# ============================================================================

from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from accounts.models import ProjectTask
from accounts.tenant import branding_template_context, get_active_organization


def _project_stage_track(project):
    """Derive a standard project lifecycle stage track for one InfraProject.

    There is no status field on InfraProject, so the stage is inferred from the
    procurement EvaluationEvent, its published TenderListing, the submissions
    and the compliance checkpoints.
    """
    from buildwatch.models import EvaluationEvent, Submission

    ev = (project.evaluation_events
          .filter(context=EvaluationEvent.PROCUREMENT)
          .order_by('id')
          .first())
    listing = getattr(ev, 'listing', None)
    published = bool(listing and listing.is_published)
    status = ev.status if ev else None
    awarded = Submission.objects.filter(event=ev, is_awarded=True).exists() if ev else False
    sub_count = ev.submissions.count() if ev else 0

    cp_total = cp_appr = 0
    if listing is not None:
        cps = listing.checkpoints.all()
        cp_total = cps.count()
        cp_appr = cps.filter(status='APPROVED').count()

    funded = bool(published or (project.contract_value and project.contract_value > 0))
    tendered = published
    eval_active = status in (EvaluationEvent.STATUS_CLOSED, EvaluationEvent.STATUS_EVALUATED)
    eval_done = bool(awarded or status in (EvaluationEvent.STATUS_EVALUATED,
                                           EvaluationEvent.STATUS_AWARDED))
    award_done = bool(awarded or status == EvaluationEvent.STATUS_AWARDED)
    exec_done = bool(cp_total and cp_appr == cp_total)

    if award_done or eval_done:
        eval_detail = 'Completed'
    elif eval_active:
        eval_detail = 'In progress'
    elif tendered:
        eval_detail = 'Awaiting close (%d bid%s)' % (sub_count, '' if sub_count == 1 else 's')
    else:
        eval_detail = 'Pending'

    if published:
        tender_detail = 'Published %s' % (listing.published_at.strftime('%d %b %Y')
                                          if listing.published_at else 'yes')
    else:
        tender_detail = 'Not yet'

    if cp_total:
        exec_detail = '%d/%d signed off' % (cp_appr, cp_total)
    elif award_done:
        exec_detail = 'Mobilising'
    else:
        exec_detail = 'Pending'

    raw = [
        ('Project Identification', True, project.task.project_id),
        ('Project Funding', funded, 'Secured' if funded else 'Pending'),
        ('Tendered', tendered, tender_detail),
        ('Tender Evaluation', eval_done, eval_detail),
        ('Award', award_done, award_done and 'Awarded' or 'Pending'),
        ('Execution & Compliance', exec_done, exec_detail),
    ]

    stages = []
    prev_done = True
    done_count = 0
    for label, done, detail in raw:
        if done:
            state = 'done'
            done_count += 1
        elif prev_done:
            state = 'current'
            prev_done = False
        else:
            state = 'pending'
        stages.append({'label': label, 'state': state, 'detail': detail})

    pct = int(round(done_count * 100 / len(raw))) if raw else 0
    return {
        'project': project,
        'stages': stages,
        'pct': pct,
        'listing': listing,
        'value': project.contract_value,
    }


@login_required
def infra_project_list(request):
    """Projects Status - the sponsor's projects with a lifecycle stage track."""
    from buildwatch.models import InfraProject
    from accounts.tenant import get_exchange_persona

    org = get_active_organization(request)
    projects = (
        InfraProject.objects
        .filter(owner_org=org, is_active=True)
        .exclude(county__iexact='Isiolo')
        .exclude(task__project_id__icontains='SK_004')
        .select_related('task', 'country')
        .order_by('-id')
    )
    rows = [_project_stage_track(p) for p in projects]
    is_sponsor = (get_exchange_persona(org=org) == 'employer') if org else False

    return render(request, 'buildwatch/project_list.html', {
        'project_rows': rows,
        'is_sponsor': is_sponsor,
        **branding_template_context(request),
    })


@login_required
def infra_project_dashboard(request, project_id):
    """
    Sprint 1 — Single project dashboard.
    Shows budget baseline, programme health, open flags, next milestone.
    """
    try:
        from buildwatch.models import InfraProject
        project = get_object_or_404(InfraProject, pk=project_id)
    except Exception:
        messages.error(request, 'BuildWatch project module not yet activated.')
        return redirect('dashboard')

    return render(request, 'buildwatch/project_dashboard.html', {
        'project': project,
        **branding_template_context(request),
    })


@login_required
def infra_project_create(request):
    """
    Sprint 1 — Register a new InfraProject.
    Links to an existing ProjectTask (Pioneer) or creates one.
    Isiolo Stadium: project_id = SK_004_2025, task already exists.
    """
    try:
        from buildwatch.models import InfraProject
    except ImportError:
        messages.error(request, 'BuildWatch app not yet installed. Run migrations first.')
        return redirect('dashboard')

    org = get_active_organization(request)
    tasks = ProjectTask.objects.all().order_by('project_id')

    if request.method == 'POST':
        task_id = request.POST.get('task_id', '').strip()
        sector = request.POST.get('sector', '').strip()
        project_type = request.POST.get('project_type', 'GOV').strip()
        county = request.POST.get('county', '').strip()
        contract_value = request.POST.get('contract_value', '0').replace(',', '')
        start_date = request.POST.get('start_date') or None
        end_date = request.POST.get('end_date') or None

        if not task_id:
            messages.error(request, 'Project task is required.')
            return render(request, 'buildwatch/project_create.html',
                          {'tasks': tasks, **branding_template_context(request)})

        task = get_object_or_404(ProjectTask, pk=task_id)

        if InfraProject.objects.filter(task=task).exists():
            messages.warning(
                request,
                f'Project {task_id} is already registered on BuildWatch.',
            )
            proj = InfraProject.objects.get(task=task)
            return redirect('infra-project-dashboard', project_id=proj.pk)

        try:
            project = InfraProject.objects.create(
                task=task,
                owner_org=org,
                sector=sector,
                project_type=project_type,
                county=county,
                contract_value=Decimal(contract_value or '0'),
                start_date=start_date,
                end_date=end_date,
                is_active=True,
            )
            messages.success(
                request,
                f'Project {task_id} registered on BuildWatch. '
                f'Next: upload the BOQ to create the deliverable register.',
            )
            return redirect('infra-project-dashboard', project_id=project.pk)
        except Exception as exc:
            messages.error(request, f'Could not create project: {exc}')

    return render(request, 'buildwatch/project_create.html', {
        'tasks': tasks,
        'sectors': [
            ('ROADS', 'Roads & Bridges'),
            ('BUILDINGS', 'Buildings'),
            ('WATER', 'Water & Sanitation'),
            ('ENERGY', 'Energy'),
            ('ICT', 'ICT Infrastructure'),
            ('OTHER', 'Other'),
        ],
        'project_types': [
            ('GOV', 'Government'),
            ('PPP', 'Public-Private Partnership'),
            ('PRIVATE', 'Private'),
        ],
        **branding_template_context(request),
    })


@login_required
def isiolo_stadium_pilot(request):
    """
    Convenience redirect to the Isiolo Stadium InfraProject dashboard.
    Creates the project if it doesn't exist yet.
    Tender ref: SK/004/2025-2026 | ProjectTask: SK_004_2025
    """
    try:
        from buildwatch.models import InfraProject
        task = ProjectTask.objects.filter(
            project_id__icontains='SK_004'
        ).first()
        if not task:
            messages.warning(
                request,
                'Isiolo Stadium ProjectTask (SK_004) not found. '
                'Create it in the Master Data panel first.',
            )
            return redirect('dashboard')

        project, created = InfraProject.objects.get_or_create(
            task=task,
            defaults={
                'owner_org': get_active_organization(request),
                'sector': 'BUILDINGS',
                'project_type': 'GOV',
                'county': 'Isiolo',
                'contract_value': Decimal('0'),
                'is_active': True,
            },
        )
        if created:
            messages.success(
                request,
                'Isiolo Stadium registered as BuildWatch pilot project.',
            )
        return redirect('infra-project-dashboard', project_id=project.pk)

    except Exception as exc:
        messages.error(
            request,
            f'BuildWatch not yet activated: {exc}. Run migrations first.',
        )
        return redirect('dashboard')
