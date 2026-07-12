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


@login_required
def infra_project_list(request):
    """
    Sprint 1 — List all InfraProjects visible to the logged-in user.
    Stub: returns empty list until buildwatch.InfraProject model is migrated.
    """
    try:
        from buildwatch.models import InfraProject
        org = get_active_organization(request)
        projects = InfraProject.objects.filter(
            owner_org=org, is_active=True
        ).order_by('-id')
    except Exception:
        projects = []

    return render(request, 'buildwatch/project_list.html', {
        'projects': projects,
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
