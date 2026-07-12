# ============================================================================
# buildwatch/models.py  — Sprint 1 + Sprint 2
#
# Drop this file into: project_accounting_B/buildwatch/models.py
#
# Depends on:
#   accounts.Organization      (existing — DO NOT MODIFY)
#   accounts.UserAccount       (existing — DO NOT MODIFY)
#   accounts.ProjectTask       (existing — DO NOT MODIFY)
#   accounts.SupplierAccount   (existing — DO NOT MODIFY)
#
# Run after creating this file:
#   python manage.py makemigrations buildwatch
#   python manage.py migrate buildwatch
# ============================================================================

from django.db import models
from django.utils import timezone
from decimal import Decimal


# ════════════════════════════════════════════════════════════════════════════
# SPRINT 1 — CORE REGISTRY
# ════════════════════════════════════════════════════════════════════════════

class Country(models.Model):
    """
    Global country registry for the tender exchange.
    Holds regulatory context — procurement law, licensing body, currency.
    """
    code            = models.CharField(max_length=3, unique=True,
                          help_text="ISO 3166-1 alpha-2/3: KE, UG, TZ, NG, GH, ZA")
    name            = models.CharField(max_length=100)
    currency_code   = models.CharField(max_length=10, default="KES",
                          help_text="ISO currency code: KES, UGX, TZS, NGN, GHS")
    currency_symbol = models.CharField(max_length=10, default="KES",
                          help_text="Symbol shown on documents: KES, UGX, NGN")
    procurement_law = models.CharField(max_length=200, blank=True,
                          help_text="e.g. PPADA 2015 (Kenya), PPDA Act (Uganda)")
    regulator_name  = models.CharField(max_length=200, blank=True,
                          help_text="e.g. National Construction Authority (NCA)")
    regulator_url   = models.URLField(blank=True)
    is_active       = models.BooleanField(default=True)

    class Meta:
        ordering    = ['name']
        verbose_name_plural = 'Countries'

    def __str__(self):
        return f"{self.code} — {self.name}"


class InfraProject(models.Model):
    """
    Extends accounts.ProjectTask into a full BuildWatch infrastructure project.
    Pilot: Isiolo Stadium SK/004/2025-2026
    """
    SECTOR_CHOICES = [
        ('ROADS',     'Roads & Bridges'),
        ('BUILDINGS', 'Buildings'),
        ('WATER',     'Water & Sanitation'),
        ('ENERGY',    'Energy'),
        ('ICT',       'ICT Infrastructure'),
        ('OTHER',     'Other'),
    ]
    PROJECT_TYPE_CHOICES = [
        ('GOV',     'Government'),
        ('PPP',     'Public-Private Partnership'),
        ('PRIVATE', 'Private'),
    ]

    task        = models.OneToOneField(
                      'accounts.ProjectTask',
                      on_delete=models.CASCADE,
                      related_name='infra_profile',
                  )
    owner_org   = models.ForeignKey(
                      'accounts.Organization',
                      on_delete=models.PROTECT,
                      related_name='owned_projects',
                      help_text='Gov MDA, County, Private Client or PPP entity',
                  )
    country     = models.ForeignKey(
                      Country,
                      on_delete=models.SET_NULL,
                      null=True, blank=True,
                  )
    sector          = models.CharField(max_length=50, choices=SECTOR_CHOICES)
    project_type    = models.CharField(max_length=20, choices=PROJECT_TYPE_CHOICES,
                          default='GOV')
    county          = models.CharField(max_length=100, blank=True)
    gps_lat         = models.DecimalField(max_digits=10, decimal_places=7,
                          null=True, blank=True)
    gps_lng         = models.DecimalField(max_digits=10, decimal_places=7,
                          null=True, blank=True)
    contract_value  = models.DecimalField(max_digits=18, decimal_places=2,
                          default=Decimal('0'))
    start_date      = models.DateField(null=True, blank=True)
    end_date        = models.DateField(null=True, blank=True)
    risk_score      = models.DecimalField(max_digits=5, decimal_places=2,
                          default=Decimal('100'),
                          help_text='0=critical, 100=healthy — computed daily')
    is_active       = models.BooleanField(default=True)
    created_at      = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.task.project_id} — {self.task.description}"


class StandardsLibrary(models.Model):
    """
    Construction standards referenced in quality gates and inspection checklists.
    Multi-standard: NCA, KEBS, KRB, BS, ASTM, ISO, country-specific.
    """
    code        = models.CharField(max_length=50, unique=True,
                      help_text='e.g. KRB-2019-4.2, NCA-E-001, BS7671')
    title       = models.CharField(max_length=255)
    body        = models.CharField(max_length=100,
                      help_text='NCA, KEBS, KRB, BS, ASTM, ISO, EBK')
    country     = models.ForeignKey(Country, on_delete=models.SET_NULL,
                      null=True, blank=True,
                      help_text='Null = international standard')
    sector      = models.CharField(max_length=50)
    parameter   = models.CharField(max_length=255,
                      help_text='e.g. Compaction density, Cable insulation resistance')
    min_value   = models.DecimalField(max_digits=10, decimal_places=4,
                      null=True, blank=True)
    max_value   = models.DecimalField(max_digits=10, decimal_places=4,
                      null=True, blank=True)
    unit        = models.CharField(max_length=30, blank=True,
                      help_text="e.g. %, mm, MPa, MΩ")
    description = models.TextField(blank=True)
    is_active   = models.BooleanField(default=True)

    class Meta:
        ordering = ['body', 'code']

    def __str__(self):
        return f"{self.code} — {self.title}"


class AuditLedger(models.Model):
    """
    Immutable event log. Every action by every user on every project.
    Records are NEVER deleted or updated — append only.
    professional_reg stored at time of action — not FK — for permanence.
    """
    project         = models.ForeignKey(InfraProject, on_delete=models.PROTECT,
                          null=True, blank=True)
    user            = models.ForeignKey('accounts.UserAccount',
                          on_delete=models.PROTECT)
    action          = models.CharField(max_length=100,
                          help_text='e.g. INSPECTION_APPROVED, CERT_ISSUED, BID_SUBMITTED')
    model_name      = models.CharField(max_length=100)
    object_id       = models.CharField(max_length=100)
    detail          = models.JSONField(default=dict)
    professional_reg = models.CharField(max_length=100, blank=True,
                          help_text='EPRA/NCA/EBK reg no. at time of action')
    ip_address      = models.GenericIPAddressField(null=True, blank=True)
    timestamp       = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering    = ['-timestamp']
        get_latest_by = 'timestamp'

    def save(self, *args, **kwargs):
        # Prevent edits — audit records are immutable
        if self.pk:
            raise ValueError("AuditLedger records cannot be modified.")
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.timestamp:%Y-%m-%d %H:%M} | {self.action} | {self.user}"


# ════════════════════════════════════════════════════════════════════════════
# SPRINT 2 — EVALUATION ENGINE (Procurement + Inspection + Certification)
# ════════════════════════════════════════════════════════════════════════════

class EvaluationEvent(models.Model):
    """
    The core evaluation engine — runs in three contexts:
      PROCUREMENT   : bid evaluation → LPO award
      INSPECTION    : site inspection → payment certificate
      CERTIFICATION : regulatory/professional certification → PC/FC

    Same scoring engine, same gates, different templates and checklists.
    """
    PROCUREMENT   = 'PROCUREMENT'
    INSPECTION    = 'INSPECTION'
    CERTIFICATION = 'CERTIFICATION'
    CONTEXT_CHOICES = [
        (PROCUREMENT,   'Procurement — bid evaluation'),
        (INSPECTION,    'Site Inspection — payment certification'),
        (CERTIFICATION, 'Regulatory / Professional Certification'),
    ]

    STATUS_OPEN       = 'OPEN'
    STATUS_CLOSED     = 'CLOSED'
    STATUS_EVALUATED  = 'EVALUATED'
    STATUS_AWARDED    = 'AWARDED'
    STATUS_CERTIFIED  = 'CERTIFIED'
    STATUS_CHOICES = [
        (STATUS_OPEN,      'Open'),
        (STATUS_CLOSED,    'Closed'),
        (STATUS_EVALUATED, 'Evaluated'),
        (STATUS_AWARDED,   'Awarded / Certified'),
    ]

    project         = models.ForeignKey(InfraProject, on_delete=models.PROTECT,
                          related_name='evaluation_events')
    context         = models.CharField(max_length=20, choices=CONTEXT_CHOICES,
                          default=PROCUREMENT)
    ref             = models.CharField(max_length=100, unique=True,
                          help_text='e.g. SK/004/2025-2026, IC-001, EPRA-CERT-001')
    description     = models.CharField(max_length=500)
    issue_date      = models.DateField()
    closing_date    = models.DateTimeField()
    status          = models.CharField(max_length=20, choices=STATUS_CHOICES,
                          default=STATUS_OPEN)
    min_pass_score  = models.DecimalField(max_digits=5, decimal_places=2,
                          default=Decimal('70'),
                          help_text='Minimum technical score % to proceed')
    outlier_pct     = models.DecimalField(max_digits=5, decimal_places=2,
                          default=Decimal('15'),
                          help_text='Flag bids >±this% from QS estimate')
    # INSPECTION context fields
    # Sprint 3+: FK to execution.Milestone once that app exists.
    # Placeholder keeps Sprint 2 installable without the execution app.
    milestone_id_legacy = models.PositiveIntegerField(
                          null=True, blank=True,
                          help_text='Reserved for execution.Milestone PK (Sprint 3+)')
    # PROCUREMENT context — links to TenderListing
    created_by      = models.ForeignKey('accounts.UserAccount',
                          on_delete=models.PROTECT,
                          related_name='created_events')
    created_at      = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.ref} [{self.get_context_display()}]"

    @property
    def is_open(self):
        return (self.status == self.STATUS_OPEN and
                self.closing_date > timezone.now())

    @property
    def days_remaining(self):
        if self.closing_date > timezone.now():
            return (self.closing_date.date() - timezone.now().date()).days
        return 0


class MandatoryRequirement(models.Model):
    """
    Library of mandatory requirements (MR items) that can be attached
    to any EvaluationEvent. Reused across procurement, inspection, certification.
    Context-specific checklists built from this library.
    """
    PROCUREMENT   = 'PROCUREMENT'
    INSPECTION    = 'INSPECTION'
    CERTIFICATION = 'CERTIFICATION'
    ALL           = 'ALL'
    CONTEXT_CHOICES = [
        (PROCUREMENT,   'Procurement'),
        (INSPECTION,    'Inspection'),
        (CERTIFICATION, 'Certification'),
        (ALL,           'All contexts'),
    ]

    code        = models.CharField(max_length=20, unique=True,
                      help_text='e.g. MR-PROC-01, MR-INSP-01, MR-CERT-01')
    context     = models.CharField(max_length=20, choices=CONTEXT_CHOICES)
    country     = models.ForeignKey(Country, on_delete=models.SET_NULL,
                      null=True, blank=True,
                      help_text='Null = global requirement')
    description = models.CharField(max_length=500)
    detail      = models.TextField(blank=True,
                      help_text='Full requirement text shown to bidder/inspector')
    is_active   = models.BooleanField(default=True)
    order       = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['context', 'order']

    def __str__(self):
        return f"{self.code} — {self.description[:60]}"


class Submission(models.Model):
    """
    A submission against an EvaluationEvent.
    PROCUREMENT: contractor's bid submission
    INSPECTION:  engineer's inspection record
    CERTIFICATION: regulatory body's assessment
    """
    event           = models.ForeignKey(EvaluationEvent, on_delete=models.CASCADE,
                          related_name='submissions')
    submitter_org   = models.ForeignKey('accounts.Organization',
                          on_delete=models.PROTECT,
                          help_text='Contractor org, Inspector org, or Certifying body')
    submitted_by    = models.ForeignKey('accounts.UserAccount',
                          on_delete=models.PROTECT)
    submitted_at    = models.DateTimeField()

    # Procurement-specific
    tender_total    = models.DecimalField(max_digits=15, decimal_places=2,
                          null=True, blank=True)
    is_late         = models.BooleanField(default=False)

    # Evaluation outcome
    disqualified    = models.BooleanField(default=False)
    disq_reason     = models.CharField(max_length=500, blank=True)
    is_awarded      = models.BooleanField(default=False)

    # Scores (computed from MandatoryCheck and TechnicalScore records)
    mr_passed       = models.BooleanField(null=True,
                          help_text='True if all mandatory checks passed')
    technical_score = models.DecimalField(max_digits=6, decimal_places=3,
                          null=True, blank=True,
                          help_text='Weighted technical score 0–100')
    rank            = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        ordering    = ['rank', '-submitted_at']
        unique_together = [['event', 'submitter_org']]

    def __str__(self):
        return f"{self.event.ref} — {self.submitter_org.short_name}"

    @property
    def passes_technical_threshold(self):
        if self.technical_score is None:
            return False
        return self.technical_score >= self.event.min_pass_score


class MandatoryCheck(models.Model):
    """
    Pass/Fail gate — one record per MR item per submission.
    Works for procurement (MR1–MR14), inspection (safety checks),
    and certification (commissioning tests).
    """
    submission  = models.ForeignKey(Submission, on_delete=models.CASCADE,
                      related_name='mr_checks')
    requirement = models.ForeignKey(MandatoryRequirement, on_delete=models.PROTECT,
                      null=True, blank=True)
    mr_ref      = models.CharField(max_length=20,
                      help_text='e.g. MR1, MR-INSP-01, COMM-01')
    description = models.CharField(max_length=500)
    PASS        = 'PASS'
    FAIL        = 'FAIL'
    RESULT_CHOICES = [(PASS, 'Pass'), (FAIL, 'Fail')]
    result      = models.CharField(max_length=5, choices=RESULT_CHOICES)
    notes       = models.TextField(blank=True)
    document_ref= models.CharField(max_length=200, blank=True,
                      help_text='Reference to uploaded compliance document')
    checked_by  = models.ForeignKey('accounts.UserAccount',
                      on_delete=models.SET_NULL, null=True, blank=True)
    checked_at  = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.mr_ref} — {self.result} ({self.submission})"


class TechnicalScore(models.Model):
    """
    Weighted technical score per criterion per submission.
    Criteria and weights differ by context:
      PROCUREMENT:   Spec compliance 40%, Personnel 25%, Experience 25%, Equipment 10%
      INSPECTION:    Workmanship 40%, Quantity verified 30%, Test results 20%, Safety 10%
      CERTIFICATION: Standards compliance 50%, Documentation 30%, Test results 20%
    """
    submission      = models.ForeignKey(Submission, on_delete=models.CASCADE,
                          related_name='tech_scores')
    criterion       = models.CharField(max_length=80,
                          help_text='e.g. SPEC_COMPLIANCE, WORKMANSHIP, STANDARDS')
    criterion_label = models.CharField(max_length=200, blank=True)
    weight          = models.DecimalField(max_digits=5, decimal_places=2,
                          help_text='Percentage weight e.g. 40.00')
    raw_score       = models.DecimalField(max_digits=5, decimal_places=2,
                          help_text='Score 0–10 assigned by evaluator')
    weighted_score  = models.DecimalField(max_digits=6, decimal_places=3,
                          help_text='raw_score × weight / 10 — computed on save')
    notes           = models.TextField(blank=True)
    scored_by       = models.ForeignKey('accounts.UserAccount',
                          on_delete=models.SET_NULL, null=True, blank=True)
    scored_at       = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        self.weighted_score = (self.raw_score * self.weight / Decimal('10')).quantize(
            Decimal('0.001')
        )
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.criterion}: {self.raw_score}/10 × {self.weight}% = {self.weighted_score}"


class SubmissionBillPrice(models.Model):
    """
    Submission's priced amount for a BOQ bill.
    PROCUREMENT: contractor's quoted amount vs QS estimate
    INSPECTION:  approved quantity × rate = certifiable amount
    """
    submission      = models.ForeignKey(Submission, on_delete=models.CASCADE,
                          related_name='bill_prices')
    bill_ref        = models.CharField(max_length=20,
                          help_text='e.g. 2A, 2B, 9 — matches BOQBill.bill_no')
    description     = models.CharField(max_length=255)
    qs_estimate     = models.DecimalField(max_digits=15, decimal_places=2,
                          default=Decimal('0'))
    submitted_amount= models.DecimalField(max_digits=15, decimal_places=2,
                          default=Decimal('0'))
    approved_amount = models.DecimalField(max_digits=15, decimal_places=2,
                          default=Decimal('0'),
                          help_text='Amount approved after evaluation/inspection')
    variance_pct    = models.DecimalField(max_digits=7, decimal_places=3,
                          default=Decimal('0'),
                          help_text='(submitted - qs_estimate) / qs_estimate × 100')
    is_outlier      = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        if self.qs_estimate and self.qs_estimate != 0:
            self.variance_pct = (
                (self.submitted_amount - self.qs_estimate) /
                self.qs_estimate * Decimal('100')
            ).quantize(Decimal('0.001'))
            self.is_outlier = abs(self.variance_pct) > Decimal('15')
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Bill {self.bill_ref}: {self.submitted_amount} (var {self.variance_pct}%)"


# ════════════════════════════════════════════════════════════════════════════
# SPRINT 2 — TENDER EXCHANGE
# ════════════════════════════════════════════════════════════════════════════

class TenderListing(models.Model):
    """
    Public-facing tender advertisement on the BuildWatch exchange.
    The shop window — browsable without login, BOQ download requires registration.
    """
    WORKS           = 'WORKS'
    CONSULTANCY     = 'CONSULTANCY'
    GOODS           = 'GOODS'
    TENDER_TYPE_CHOICES = [
        (WORKS,       'Works — Civil, Electrical, Mechanical, Roads'),
        (CONSULTANCY, 'Consultancy — Design, Supervision, QS, PM'),
        (GOODS,       'Goods & Supply — Materials, Equipment, Plant'),
    ]

    PUBLIC      = 'PUBLIC'
    PRIVATE     = 'PRIVATE'
    RESTRICTED  = 'RESTRICTED'
    VISIBILITY_CHOICES = [
        (PUBLIC,     'Public — open to all registered bidders globally'),
        (PRIVATE,    'Private — invitation only'),
        (RESTRICTED, 'Restricted — specific country or county'),
    ]

    GOV         = 'GOV'
    PRIVATE_F   = 'PRIVATE'
    PPP         = 'PPP'
    DONOR       = 'DONOR'
    NGO         = 'NGO'
    FUNDING_CHOICES = [
        (GOV,      'Government — National or County'),
        (PRIVATE_F,'Private Sector'),
        (PPP,      'Public-Private Partnership'),
        (DONOR,    'Donor / Development Finance (WB, AfDB, EU, USAID)'),
        (NGO,      'NGO / International Organisation'),
    ]

    event           = models.OneToOneField(EvaluationEvent,
                          on_delete=models.CASCADE,
                          related_name='listing')
    tender_type     = models.CharField(max_length=20, choices=TENDER_TYPE_CHOICES,
                          default=WORKS)
    visibility      = models.CharField(max_length=20, choices=VISIBILITY_CHOICES,
                          default=PUBLIC)
    funding_source  = models.CharField(max_length=20, choices=FUNDING_CHOICES,
                          default=GOV)

    # Location
    country         = models.ForeignKey(Country, on_delete=models.SET_NULL,
                          null=True, blank=True)
    county_region   = models.CharField(max_length=100, blank=True,
                          help_text='County, region or city')

    # Value range shown to bidders (not exact — avoids anchoring)
    estimated_value_min = models.DecimalField(max_digits=15, decimal_places=2,
                              null=True, blank=True)
    estimated_value_max = models.DecimalField(max_digits=15, decimal_places=2,
                              null=True, blank=True)
    currency        = models.CharField(max_length=10, default='KES')

    # Key dates
    is_published    = models.BooleanField(default=False)
    published_at    = models.DateTimeField(null=True, blank=True)
    clarification_deadline = models.DateTimeField(null=True, blank=True)
    site_visit_date = models.DateTimeField(null=True, blank=True)
    site_visit_location = models.CharField(max_length=300, blank=True)

    # Documents
    boq_document    = models.FileField(upload_to='tenders/boq/%Y/%m/',
                          null=True, blank=True,
                          help_text='Structured BOQ PDF or XLSX')
    specification   = models.FileField(upload_to='tenders/spec/%Y/%m/',
                          null=True, blank=True)
    drawings        = models.FileField(upload_to='tenders/drawings/%Y/%m/',
                          null=True, blank=True)
    addendum_count  = models.IntegerField(default=0)

    # Engagement metrics (no personal data)
    view_count              = models.IntegerField(default=0)
    registered_bidder_count = models.IntegerField(default=0)
    submission_count        = models.IntegerField(default=0)

    # Short summary for listing card
    summary         = models.TextField(blank=True, max_length=500,
                          help_text='2–3 sentence summary shown on listing card')

    created_at      = models.DateTimeField(auto_now_add=True)
    created_by      = models.ForeignKey('accounts.UserAccount',
                          on_delete=models.PROTECT,
                          related_name='published_tenders')

    class Meta:
        ordering = ['-published_at', '-created_at']

    def __str__(self):
        return f"{self.event.ref} — {self.event.description[:60]}"

    def publish(self, user):
        """Publish tender to exchange. Records timestamp and publisher."""
        self.is_published = True
        self.published_at = timezone.now()
        self.save()
        AuditLedger.objects.create(
            project=self.event.project,
            user=user,
            action='TENDER_PUBLISHED',
            model_name='TenderListing',
            object_id=str(self.pk),
            detail={'ref': self.event.ref, 'visibility': self.visibility},
            professional_reg=user.professional_reg_no,
        )

    @property
    def value_range_display(self):
        if self.estimated_value_min and self.estimated_value_max:
            return (f"{self.currency} "
                    f"{self.estimated_value_min:,.0f}–"
                    f"{self.estimated_value_max:,.0f}")
        return "Value not disclosed"

    @property
    def is_closing_soon(self):
        return 0 < self.event.days_remaining <= 7


class TenderInvitation(models.Model):
    """
    For PRIVATE tenders — specific organisations invited to bid.
    Organisation cannot see the tender until invited.
    """
    tender          = models.ForeignKey(TenderListing, on_delete=models.CASCADE,
                          related_name='invitations')
    organisation    = models.ForeignKey('accounts.Organization',
                          on_delete=models.PROTECT)
    invited_by      = models.ForeignKey('accounts.UserAccount',
                          on_delete=models.PROTECT)
    invited_at      = models.DateTimeField(auto_now_add=True)
    notification_sent = models.BooleanField(default=False)
    notification_sent_at = models.DateTimeField(null=True, blank=True)
    viewed_at       = models.DateTimeField(null=True, blank=True)
    accepted        = models.BooleanField(null=True,
                          help_text='None=no response, True=accepted, False=declined')

    class Meta:
        unique_together = [['tender', 'organisation']]

    def __str__(self):
        return f"{self.tender.event.ref} → {self.organisation.short_name}"


class TenderAddendum(models.Model):
    """
    Clarifications and amendments issued after publication.
    All registered bidders notified automatically via AlertEngine.
    Numbering: 1, 2, 3 per tender.
    """
    tender          = models.ForeignKey(TenderListing, on_delete=models.CASCADE,
                          related_name='addenda')
    addendum_no     = models.PositiveSmallIntegerField()
    subject         = models.CharField(max_length=255)
    content         = models.TextField()
    document        = models.FileField(upload_to='tenders/addenda/%Y/%m/',
                          null=True, blank=True)
    issued_by       = models.ForeignKey('accounts.UserAccount',
                          on_delete=models.PROTECT)
    issued_at       = models.DateTimeField(auto_now_add=True)
    notified_count  = models.IntegerField(default=0,
                          help_text='Number of registered bidders notified')

    class Meta:
        ordering        = ['addendum_no']
        unique_together = [['tender', 'addendum_no']]

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Keep addendum_count in sync on parent
        TenderListing.objects.filter(pk=self.tender_id).update(
            addendum_count=TenderAddendum.objects.filter(
                tender=self.tender).count()
        )

    def __str__(self):
        return f"{self.tender.event.ref} — Addendum {self.addendum_no}: {self.subject}"


class TenderAlert(models.Model):
    """
    Saved search — organisation gets notified when a matching tender is published.
    The AlertEngine queries these on every new TenderListing.publish() call.
    """
    EMAIL       = 'EMAIL'
    SMS         = 'SMS'
    WHATSAPP    = 'WHATSAPP'
    CHANNEL_CHOICES = [
        (EMAIL,    'Email'),
        (SMS,      'SMS'),
        (WHATSAPP, 'WhatsApp'),
    ]

    organisation    = models.ForeignKey('accounts.Organization',
                          on_delete=models.CASCADE,
                          related_name='tender_alerts')
    created_by      = models.ForeignKey('accounts.UserAccount',
                          on_delete=models.PROTECT)
    # Filter criteria — all optional, AND logic
    sector          = models.CharField(max_length=50, blank=True)
    tender_type     = models.CharField(max_length=20, blank=True)
    country         = models.ForeignKey(Country, on_delete=models.SET_NULL,
                          null=True, blank=True)
    county_region   = models.CharField(max_length=100, blank=True)
    value_min       = models.DecimalField(max_digits=15, decimal_places=2,
                          null=True, blank=True)
    value_max       = models.DecimalField(max_digits=15, decimal_places=2,
                          null=True, blank=True)
    funding_source  = models.CharField(max_length=20, blank=True)
    channel         = models.CharField(max_length=20, choices=CHANNEL_CHOICES,
                          default=EMAIL)
    is_active       = models.BooleanField(default=True)
    last_triggered  = models.DateTimeField(null=True, blank=True)
    alert_count     = models.IntegerField(default=0)
    created_at      = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        parts = [self.sector, self.tender_type,
                 self.country.code if self.country else '',
                 self.county_region]
        criteria = ' | '.join(p for p in parts if p)
        return f"{self.organisation.short_name}: {criteria or 'all tenders'}"

    def matches(self, listing):
        """Returns True if a TenderListing matches this alert's criteria."""
        if self.sector and listing.event.project.sector != self.sector:
            return False
        if self.tender_type and listing.tender_type != self.tender_type:
            return False
        if self.country and listing.country != self.country:
            return False
        if self.county_region and self.county_region.lower() not in (
                listing.county_region or '').lower():
            return False
        if self.funding_source and listing.funding_source != self.funding_source:
            return False
        if self.value_min and listing.estimated_value_max:
            if listing.estimated_value_max < self.value_min:
                return False
        if self.value_max and listing.estimated_value_min:
            if listing.estimated_value_min > self.value_max:
                return False
        return True


class BidderRegistration(models.Model):
    """
    Contractor registers interest in a specific tender.
    Not yet a bid — signals intent, gets addenda notifications.
    Required before BOQ download or bid workspace opens.
    """
    tender          = models.ForeignKey(TenderListing, on_delete=models.CASCADE,
                          related_name='bidder_registrations')
    organisation    = models.ForeignKey('accounts.Organization',
                          on_delete=models.PROTECT)
    registered_by   = models.ForeignKey('accounts.UserAccount',
                          on_delete=models.PROTECT)
    registered_at   = models.DateTimeField(auto_now_add=True)
    has_downloaded_boq = models.BooleanField(default=False)
    boq_downloaded_at  = models.DateTimeField(null=True, blank=True)
    has_submitted   = models.BooleanField(default=False)

    class Meta:
        unique_together = [['tender', 'organisation']]
        ordering        = ['-registered_at']

    def __str__(self):
        return f"{self.tender.event.ref} ← {self.organisation.short_name}"

    def record_boq_download(self):
        if not self.has_downloaded_boq:
            self.has_downloaded_boq = True
            self.boq_downloaded_at  = timezone.now()
            self.save(update_fields=['has_downloaded_boq', 'boq_downloaded_at'])
            TenderListing.objects.filter(pk=self.tender_id).update(
                registered_bidder_count=BidderRegistration.objects.filter(
                    tender=self.tender).count()
            )


class BidWorkspace(models.Model):
    """
    Contractor's private workspace for building a bid.
    INVISIBLE to Employer until contractor explicitly submits.
    Self-assessment (MR pre-check) must pass before submission allowed.
    """
    DRAFT           = 'DRAFT'
    SELF_CHECKED    = 'SELF_CHECKED'
    SUBMITTED       = 'SUBMITTED'
    WITHDRAWN       = 'WITHDRAWN'
    STATUS_CHOICES = [
        (DRAFT,         'Draft — pricing in progress'),
        (SELF_CHECKED,  'Self-assessment complete — ready to submit'),
        (SUBMITTED,     'Submitted to Employer'),
        (WITHDRAWN,     'Withdrawn'),
    ]

    tender          = models.ForeignKey(TenderListing, on_delete=models.CASCADE,
                          related_name='workspaces')
    organisation    = models.ForeignKey('accounts.Organization',
                          on_delete=models.PROTECT)
    prepared_by     = models.ForeignKey('accounts.UserAccount',
                          on_delete=models.PROTECT)
    status          = models.CharField(max_length=20, choices=STATUS_CHOICES,
                          default=DRAFT)
    self_assessment_passed = models.BooleanField(default=False)
    pricing_complete       = models.BooleanField(default=False)
    total_bid_amount       = models.DecimalField(max_digits=15, decimal_places=2,
                                default=Decimal('0'))
    # Pricing intelligence flags
    below_market_flag   = models.BooleanField(default=False,
                              help_text='True if total is >30% below market range')
    above_market_flag   = models.BooleanField(default=False,
                              help_text='True if total is >30% above market range')
    started_at          = models.DateTimeField(auto_now_add=True)
    submitted_at        = models.DateTimeField(null=True, blank=True)
    # Links to Submission record once submitted
    submission          = models.OneToOneField(Submission,
                              on_delete=models.SET_NULL,
                              null=True, blank=True,
                              related_name='workspace')

    class Meta:
        unique_together = [['tender', 'organisation']]
        ordering        = ['-started_at']

    def __str__(self):
        return (f"{self.tender.event.ref} workspace — "
                f"{self.organisation.short_name} [{self.status}]")

    def submit(self, submitted_by):
        """
        Convert workspace into a formal Submission on the Employer's queue.
        Raises ValueError if self-assessment not passed.
        """
        if not self.self_assessment_passed:
            raise ValueError(
                "Self-assessment must be completed before submitting. "
                "Fix all failing mandatory checks first."
            )
        if not self.pricing_complete:
            raise ValueError(
                "All BOQ items must be priced before submitting."
            )
        submission = Submission.objects.create(
            event=self.tender.event,
            submitter_org=self.organisation,
            submitted_by=submitted_by,
            submitted_at=timezone.now(),
            tender_total=self.total_bid_amount,
        )
        self.submission     = submission
        self.status         = self.SUBMITTED
        self.submitted_at   = timezone.now()
        self.save()
        # Update tender submission count
        TenderListing.objects.filter(pk=self.tender_id).update(
            submission_count=Submission.objects.filter(
                event=self.tender.event).count()
        )
        # Log to audit ledger
        AuditLedger.objects.create(
            project=self.tender.event.project,
            user=submitted_by,
            action='BID_SUBMITTED',
            model_name='BidWorkspace',
            object_id=str(self.pk),
            detail={
                'tender_ref':   self.tender.event.ref,
                'org':          self.organisation.short_name,
                'total':        str(self.total_bid_amount),
            },
            professional_reg=submitted_by.professional_reg_no,
        )
        return submission


class SelfAssessmentCheck(models.Model):
    """
    Contractor's self-assessment of a mandatory requirement before submitting.
    Mirrors MandatoryCheck but contractor-facing and private until submission.
    Employer sees this after submission as transparency record — shows
    contractor's own assessment vs employer's independent verification.
    """
    workspace       = models.ForeignKey(BidWorkspace, on_delete=models.CASCADE,
                          related_name='self_checks')
    requirement     = models.ForeignKey(MandatoryRequirement,
                          on_delete=models.PROTECT,
                          null=True, blank=True)
    mr_ref          = models.CharField(max_length=20)
    description     = models.CharField(max_length=500)
    PASS            = 'PASS'
    FAIL            = 'FAIL'
    PENDING         = 'PENDING'
    RESULT_CHOICES = [
        (PASS,    'Pass — document available'),
        (FAIL,    'Fail — document missing or expired'),
        (PENDING, 'Pending — document being obtained'),
    ]
    self_result     = models.CharField(max_length=10, choices=RESULT_CHOICES,
                          default=PENDING)
    document_uploaded = models.BooleanField(default=False)
    document        = models.FileField(upload_to='bids/self_assess/%Y/%m/',
                          null=True, blank=True)
    expiry_date     = models.DateField(null=True, blank=True)
    notes           = models.CharField(max_length=300, blank=True,
                          help_text='e.g. Partnering with licensed sub for EPRA T2')
    assessed_at     = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.mr_ref}: {self.self_result} ({self.workspace.organisation.short_name})"


class WorkspaceBillPrice(models.Model):
    """
    Contractor's priced BOQ bill item in their bid workspace.
    Drives pricing intelligence — compared against market range before submission.
    """
    workspace       = models.ForeignKey(BidWorkspace, on_delete=models.CASCADE,
                          related_name='bill_prices')
    bill_ref        = models.CharField(max_length=20)
    description     = models.CharField(max_length=255)
    unit            = models.CharField(max_length=30, blank=True)
    quantity        = models.DecimalField(max_digits=12, decimal_places=3,
                          default=Decimal('0'))
    unit_rate       = models.DecimalField(max_digits=12, decimal_places=2,
                          default=Decimal('0'))
    amount          = models.DecimalField(max_digits=15, decimal_places=2,
                          default=Decimal('0'))
    # Market intelligence (set from anonymised historical data)
    market_rate_low  = models.DecimalField(max_digits=12, decimal_places=2,
                           null=True, blank=True)
    market_rate_high = models.DecimalField(max_digits=12, decimal_places=2,
                           null=True, blank=True)
    is_below_market  = models.BooleanField(default=False)
    is_above_market  = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        self.amount = (self.quantity * self.unit_rate).quantize(Decimal('0.01'))
        # Market intelligence flags
        if self.market_rate_low and self.unit_rate < self.market_rate_low * Decimal('0.70'):
            self.is_below_market = True
        if self.market_rate_high and self.unit_rate > self.market_rate_high * Decimal('1.30'):
            self.is_above_market = True
        super().save(*args, **kwargs)
        # Recalculate workspace total
        total = WorkspaceBillPrice.objects.filter(
            workspace=self.workspace
        ).aggregate(t=models.Sum('amount'))['t'] or Decimal('0')
        BidWorkspace.objects.filter(pk=self.workspace_id).update(
            total_bid_amount=total
        )

    def __str__(self):
        return f"Bill {self.bill_ref}: {self.amount:,.2f}"
