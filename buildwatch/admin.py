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
    list_filter = ['is_active']
    search_fields = ['code', 'name']


@admin.register(InfraProject)
class InfraProjectAdmin(admin.ModelAdmin):
    list_display = ['task', 'owner_org', 'sector', 'project_type', 'county', 'risk_score', 'is_active']
    list_filter = ['sector', 'project_type', 'is_active']
    search_fields = ['task__project_id', 'task__description', 'county']


@admin.register(StandardsLibrary)
class StandardsLibraryAdmin(admin.ModelAdmin):
    list_display = ['code', 'title', 'body', 'sector', 'parameter', 'is_active']
    list_filter = ['body', 'sector', 'is_active']
    search_fields = ['code', 'title', 'parameter']


@admin.register(AuditLedger)
class AuditLedgerAdmin(admin.ModelAdmin):
    list_display = ['timestamp', 'action', 'user', 'model_name', 'professional_reg']
    list_filter = ['action', 'model_name']
    readonly_fields = [
        'timestamp', 'project', 'user', 'action', 'model_name',
        'object_id', 'detail', 'professional_reg', 'ip_address',
    ]

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(EvaluationEvent)
class EvaluationEventAdmin(admin.ModelAdmin):
    list_display = ['ref', 'context', 'project', 'status', 'closing_date', 'created_at']
    list_filter = ['context', 'status']
    search_fields = ['ref', 'description']


@admin.register(MandatoryRequirement)
class MandatoryRequirementAdmin(admin.ModelAdmin):
    list_display = ['code', 'context', 'country', 'description', 'order', 'is_active']
    list_filter = ['context', 'country', 'is_active']
    ordering = ['context', 'order']


@admin.register(TenderListing)
class TenderListingAdmin(admin.ModelAdmin):
    list_display = [
        'event', 'tender_type', 'visibility', 'funding_source',
        'country', 'is_published', 'view_count',
        'registered_bidder_count', 'submission_count',
    ]
    list_filter = ['tender_type', 'visibility', 'funding_source', 'is_published']
    search_fields = ['event__ref', 'event__description', 'county_region']
    readonly_fields = [
        'view_count', 'registered_bidder_count',
        'submission_count', 'addendum_count', 'published_at',
    ]
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
    list_filter = ['has_downloaded_boq', 'has_submitted']


@admin.register(BidWorkspace)
class BidWorkspaceAdmin(admin.ModelAdmin):
    list_display = [
        'tender', 'organisation', 'status', 'total_bid_amount',
        'self_assessment_passed', 'pricing_complete', 'started_at',
    ]
    list_filter = ['status', 'self_assessment_passed']


admin.site.register(Submission)
admin.site.register(MandatoryCheck)
admin.site.register(TechnicalScore)
admin.site.register(SubmissionBillPrice)
admin.site.register(TenderInvitation)
admin.site.register(TenderAddendum)
admin.site.register(TenderAlert)
admin.site.register(SelfAssessmentCheck)
admin.site.register(WorkspaceBillPrice)
