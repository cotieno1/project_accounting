from accounts.models import Organization
from buildwatch.models import MandatoryRequirement, TenderListing, SelfAssessmentCheck

o = Organization.objects.filter(name__icontains='Pioneer').first()
print('ORG', None if not o else f'{o.name}|{o.organization_type}|{o.org_code}')
print('MR_PROC', MandatoryRequirement.objects.filter(
    context__in=['PROCUREMENT', 'ALL'], is_active=True
).count())
listing = TenderListing.objects.filter(pk=1).select_related('event').first()
if listing:
    print('LISTING', listing.pk, listing.is_published, listing.event.status, listing.event.closing_date)
print('SELF_CHECKS', SelfAssessmentCheck.objects.count())
print('SELF_DOCS', SelfAssessmentCheck.objects.filter(document_uploaded=True).count())
