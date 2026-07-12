# ============================================================================
# SPRINT 2 SETUP — two files to update
# ============================================================================


# ════════════════════════════════════════════════════════════════════════════
# FILE 1: UN_accounting_system/settings.py
# ADD to INSTALLED_APPS:
# ════════════════════════════════════════════════════════════════════════════

INSTALLED_APPS = [
    # ... existing apps unchanged ...
    'accounts',               # existing Pioneer financial engine

    # BuildWatch — new apps
    'buildwatch',             # Sprint 1+2: core registry + tender exchange
    # 'procurement',          # Sprint 2+: BOQ, bid evaluation (future dedicated app)
    # 'execution',            # Sprint 3+: programme, inspection, certificates
    # 'compliance',           # Sprint 5+: risk engine, quality gates
    # 'analytics',            # Sprint 5+: national dashboard
    # 'api',                  # Sprint 6+: mobile PWA REST API
]

# Media files (BOQ uploads, bid documents, inspection photos)
MEDIA_URL  = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# BuildWatch platform settings
BUILDWATCH_ENV          = 'staging'   # 'staging' or 'production'
BUILDWATCH_PLATFORM_URL = 'https://projectaccounting-production.up.railway.app'

# Africa's Talking — SMS/WhatsApp tender alerts
# Set these in Railway environment variables, not here
# AT_API_KEY  = env('WHATSAPP_API_KEY', default='')
# AT_USERNAME = env('AT_USERNAME', default='sandbox')


# ════════════════════════════════════════════════════════════════════════════
# FILE 2: UN_accounting_system/urls.py
# ADD these lines to urlpatterns:
# ════════════════════════════════════════════════════════════════════════════

from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from buildwatch.urls import buildwatch_patterns, tender_patterns

urlpatterns = [
    # ... ALL EXISTING ROUTES UNCHANGED ...

    # BuildWatch — project management
    # URL: /buildwatch/projects/, /buildwatch/isiolo/ etc.
    path('buildwatch/', include((buildwatch_patterns, 'buildwatch'))),

    # Tender Exchange
    # URL: /tenders/, /tenders/<id>/, /tenders/publish/ etc.
    path('tenders/', include((tender_patterns, 'tenders'))),

    # BuildWatch self-registration (public — no login)
    # URL: /register/, /register/pending/
    path('register/',         include('accounts.urls_register')),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)


# ════════════════════════════════════════════════════════════════════════════
# FILE 3: accounts/urls_register.py  (new small file)
# Separates registration URLs from main accounts urls.py
# ════════════════════════════════════════════════════════════════════════════

# accounts/urls_register.py
from django.urls import path
from accounts.views_auth import buildwatch_register, buildwatch_register_pending

urlpatterns = [
    path('',         buildwatch_register,         name='buildwatch-register'),
    path('pending/', buildwatch_register_pending,  name='buildwatch-register-pending'),
]


# ════════════════════════════════════════════════════════════════════════════
# RAILWAY DEPLOYMENT CHECKLIST
# Run these commands in Railway after pushing the code:
# ════════════════════════════════════════════════════════════════════════════

# 1. python manage.py migrate accounts          # runs 0039 (professional fields)
# 2. python manage.py migrate buildwatch        # runs 0001_initial_buildwatch
# 3. python manage.py seed_buildwatch           # seeds countries, MR library, Isiolo pilot
# 4. python manage.py collectstatic --noinput
# 5. gunicorn UN_accounting_system.wsgi:application

# Verify these URLs are live after deployment:
# https://projectaccounting-production.up.railway.app/tenders/           ← tender list
# https://projectaccounting-production.up.railway.app/tenders/1/         ← Isiolo Stadium
# https://projectaccounting-production.up.railway.app/tenders/publish/   ← publish a tender
# https://projectaccounting-production.up.railway.app/register/          ← self-registration
# https://projectaccounting-production.up.railway.app/buildwatch/isiolo/ ← pilot shortcut


# ════════════════════════════════════════════════════════════════════════════
# buildwatch/apps.py  (create this file)
# ════════════════════════════════════════════════════════════════════════════

# buildwatch/apps.py
from django.apps import AppConfig

class BuildwatchConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name    = 'buildwatch'
    label   = 'buildwatch'
    verbose_name = 'BuildWatch — Infrastructure Integrity Platform'

    def ready(self):
        # Signal handlers will be imported here in Sprint 3+
        pass


# ════════════════════════════════════════════════════════════════════════════
# buildwatch/__init__.py  (create this empty file)
# ════════════════════════════════════════════════════════════════════════════

# buildwatch/__init__.py
# (empty — Django app marker)


# ════════════════════════════════════════════════════════════════════════════
# buildwatch/admin.py  (register all models for admin panel inspection)
# ════════════════════════════════════════════════════════════════════════════

# buildwatch/admin.py
from django.contrib import admin
from .models import (
    Country, InfraProject, StandardsLibrary, AuditLedger,
    EvaluationEvent, MandatoryRequirement, Submission,
    MandatoryCheck, TechnicalScore, SubmissionBillPrice,
    TenderListing, TenderInvitation, TenderAddendum,
    TenderAlert, BidderRegistration, BidWorkspace,
    SelfAssessmentCheck, WorkspaceBillPrice,
)

@admin.register(Country)
class CountryAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'currency_code', 'procurement_law', 'is_active']
    list_filter  = ['is_active']
    search_fields= ['code', 'name']

@admin.register(InfraProject)
class InfraProjectAdmin(admin.ModelAdmin):
    list_display = ['task', 'owner_org', 'sector', 'project_type', 'county', 'risk_score', 'is_active']
    list_filter  = ['sector', 'project_type', 'is_active']
    search_fields= ['task__project_id', 'task__description', 'county']

@admin.register(StandardsLibrary)
class StandardsLibraryAdmin(admin.ModelAdmin):
    list_display = ['code', 'title', 'body', 'sector', 'parameter', 'is_active']
    list_filter  = ['body', 'sector', 'is_active']
    search_fields= ['code', 'title', 'parameter']

@admin.register(AuditLedger)
class AuditLedgerAdmin(admin.ModelAdmin):
    list_display  = ['timestamp', 'action', 'user', 'model_name', 'professional_reg']
    list_filter   = ['action', 'model_name']
    readonly_fields = ['timestamp', 'project', 'user', 'action', 'model_name',
                       'object_id', 'detail', 'professional_reg', 'ip_address']
    # No delete permission — audit ledger is immutable
    def has_delete_permission(self, request, obj=None):
        return False
    def has_change_permission(self, request, obj=None):
        return False

@admin.register(EvaluationEvent)
class EvaluationEventAdmin(admin.ModelAdmin):
    list_display = ['ref', 'context', 'project', 'status', 'closing_date', 'created_at']
    list_filter  = ['context', 'status']
    search_fields= ['ref', 'description']

@admin.register(MandatoryRequirement)
class MandatoryRequirementAdmin(admin.ModelAdmin):
    list_display = ['code', 'context', 'country', 'description', 'order', 'is_active']
    list_filter  = ['context', 'country', 'is_active']
    ordering     = ['context', 'order']

@admin.register(TenderListing)
class TenderListingAdmin(admin.ModelAdmin):
    list_display  = ['event', 'tender_type', 'visibility', 'funding_source',
                     'country', 'is_published', 'view_count',
                     'registered_bidder_count', 'submission_count']
    list_filter   = ['tender_type', 'visibility', 'funding_source', 'is_published']
    search_fields = ['event__ref', 'event__description', 'county_region']
    readonly_fields = ['view_count', 'registered_bidder_count',
                       'submission_count', 'addendum_count', 'published_at']
    actions = ['publish_selected']

    def publish_selected(self, request, queryset):
        ua = request.user.useraccount
        for listing in queryset.filter(is_published=False):
            listing.publish(ua)
        self.message_user(request, f'{queryset.count()} tender(s) published.')
    publish_selected.short_description = 'Publish selected tenders to exchange'

@admin.register(BidderRegistration)
class BidderRegistrationAdmin(admin.ModelAdmin):
    list_display = ['tender', 'organisation', 'registered_at', 'has_downloaded_boq', 'has_submitted']
    list_filter  = ['has_downloaded_boq', 'has_submitted']

@admin.register(BidWorkspace)
class BidWorkspaceAdmin(admin.ModelAdmin):
    list_display = ['tender', 'organisation', 'status', 'total_bid_amount',
                    'self_assessment_passed', 'pricing_complete', 'started_at']
    list_filter  = ['status', 'self_assessment_passed']

admin.site.register(Submission)
admin.site.register(MandatoryCheck)
admin.site.register(TechnicalScore)
admin.site.register(SubmissionBillPrice)
admin.site.register(TenderInvitation)
admin.site.register(TenderAddendum)
admin.site.register(TenderAlert)
admin.site.register(SelfAssessmentCheck)
admin.site.register(WorkspaceBillPrice)
