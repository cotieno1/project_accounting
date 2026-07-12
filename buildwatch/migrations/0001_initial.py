# ============================================================================
# buildwatch/migrations/0001_initial.py
#
# Sprint 1 + Sprint 2 — all buildwatch models in one initial migration.
# Run: python manage.py migrate buildwatch
# ============================================================================

from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone
from decimal import Decimal


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        # Repo already past 0039; pin to latest accounts migration.
        ('accounts', '0046_merge_duplicate_organizations'),
    ]

    operations = [

        # ── Country ──────────────────────────────────────────────────────────
        migrations.CreateModel(
            name='Country',
            fields=[
                ('id',              models.AutoField(primary_key=True)),
                ('code',            models.CharField(max_length=3, unique=True)),
                ('name',            models.CharField(max_length=100)),
                ('currency_code',   models.CharField(max_length=10, default='KES')),
                ('currency_symbol', models.CharField(max_length=10, default='KES')),
                ('procurement_law', models.CharField(max_length=200, blank=True)),
                ('regulator_name',  models.CharField(max_length=200, blank=True)),
                ('regulator_url',   models.URLField(blank=True)),
                ('is_active',       models.BooleanField(default=True)),
            ],
            options={'ordering': ['name'], 'verbose_name_plural': 'Countries'},
        ),

        # ── InfraProject ─────────────────────────────────────────────────────
        migrations.CreateModel(
            name='InfraProject',
            fields=[
                ('id',             models.AutoField(primary_key=True)),
                ('task',           models.OneToOneField(
                                       'accounts.ProjectTask',
                                       on_delete=django.db.models.deletion.CASCADE,
                                       related_name='infra_profile')),
                ('owner_org',      models.ForeignKey(
                                       'accounts.Organization',
                                       on_delete=django.db.models.deletion.PROTECT,
                                       related_name='owned_projects')),
                ('country',        models.ForeignKey(
                                       'buildwatch.Country',
                                       on_delete=django.db.models.deletion.SET_NULL,
                                       null=True, blank=True)),
                ('sector',         models.CharField(max_length=50)),
                ('project_type',   models.CharField(max_length=20, default='GOV')),
                ('county',         models.CharField(max_length=100, blank=True)),
                ('gps_lat',        models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)),
                ('gps_lng',        models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)),
                ('contract_value', models.DecimalField(max_digits=18, decimal_places=2, default=Decimal('0'))),
                ('start_date',     models.DateField(null=True, blank=True)),
                ('end_date',       models.DateField(null=True, blank=True)),
                ('risk_score',     models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('100'))),
                ('is_active',      models.BooleanField(default=True)),
                ('created_at',     models.DateTimeField(auto_now_add=True)),
            ],
            options={'ordering': ['-created_at']},
        ),

        # ── StandardsLibrary ─────────────────────────────────────────────────
        migrations.CreateModel(
            name='StandardsLibrary',
            fields=[
                ('id',          models.AutoField(primary_key=True)),
                ('code',        models.CharField(max_length=50, unique=True)),
                ('title',       models.CharField(max_length=255)),
                ('body',        models.CharField(max_length=100)),
                ('country',     models.ForeignKey('buildwatch.Country',
                                    on_delete=django.db.models.deletion.SET_NULL,
                                    null=True, blank=True)),
                ('sector',      models.CharField(max_length=50)),
                ('parameter',   models.CharField(max_length=255)),
                ('min_value',   models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)),
                ('max_value',   models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)),
                ('unit',        models.CharField(max_length=30, blank=True)),
                ('description', models.TextField(blank=True)),
                ('is_active',   models.BooleanField(default=True)),
            ],
            options={'ordering': ['body', 'code']},
        ),

        # ── AuditLedger ───────────────────────────────────────────────────────
        migrations.CreateModel(
            name='AuditLedger',
            fields=[
                ('id',               models.AutoField(primary_key=True)),
                ('project',          models.ForeignKey('buildwatch.InfraProject',
                                         on_delete=django.db.models.deletion.PROTECT,
                                         null=True, blank=True)),
                ('user',             models.ForeignKey('accounts.UserAccount',
                                         on_delete=django.db.models.deletion.PROTECT)),
                ('action',           models.CharField(max_length=100)),
                ('model_name',       models.CharField(max_length=100)),
                ('object_id',        models.CharField(max_length=100)),
                ('detail',           models.JSONField(default=dict)),
                ('professional_reg', models.CharField(max_length=100, blank=True)),
                ('ip_address',       models.GenericIPAddressField(null=True, blank=True)),
                ('timestamp',        models.DateTimeField(auto_now_add=True)),
            ],
            options={'ordering': ['-timestamp'], 'get_latest_by': 'timestamp'},
        ),

        # ── EvaluationEvent ───────────────────────────────────────────────────
        migrations.CreateModel(
            name='EvaluationEvent',
            fields=[
                ('id',             models.AutoField(primary_key=True)),
                ('project',        models.ForeignKey('buildwatch.InfraProject',
                                       on_delete=django.db.models.deletion.PROTECT,
                                       related_name='evaluation_events')),
                ('context',        models.CharField(max_length=20, default='PROCUREMENT')),
                ('ref',            models.CharField(max_length=100, unique=True)),
                ('description',    models.CharField(max_length=500)),
                ('issue_date',     models.DateField()),
                ('closing_date',   models.DateTimeField()),
                ('status',         models.CharField(max_length=20, default='OPEN')),
                ('min_pass_score', models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('70'))),
                ('outlier_pct',    models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('15'))),
                ('created_by',     models.ForeignKey('accounts.UserAccount',
                                       on_delete=django.db.models.deletion.PROTECT,
                                       related_name='created_events')),
                ('created_at',     models.DateTimeField(auto_now_add=True)),
            ],
            options={'ordering': ['-created_at']},
        ),

        # ── MandatoryRequirement ──────────────────────────────────────────────
        migrations.CreateModel(
            name='MandatoryRequirement',
            fields=[
                ('id',          models.AutoField(primary_key=True)),
                ('code',        models.CharField(max_length=20, unique=True)),
                ('context',     models.CharField(max_length=20)),
                ('country',     models.ForeignKey('buildwatch.Country',
                                    on_delete=django.db.models.deletion.SET_NULL,
                                    null=True, blank=True)),
                ('description', models.CharField(max_length=500)),
                ('detail',      models.TextField(blank=True)),
                ('is_active',   models.BooleanField(default=True)),
                ('order',       models.PositiveSmallIntegerField(default=0)),
            ],
            options={'ordering': ['context', 'order']},
        ),

        # ── Submission ────────────────────────────────────────────────────────
        migrations.CreateModel(
            name='Submission',
            fields=[
                ('id',              models.AutoField(primary_key=True)),
                ('event',           models.ForeignKey('buildwatch.EvaluationEvent',
                                        on_delete=django.db.models.deletion.CASCADE,
                                        related_name='submissions')),
                ('submitter_org',   models.ForeignKey('accounts.Organization',
                                        on_delete=django.db.models.deletion.PROTECT)),
                ('submitted_by',    models.ForeignKey('accounts.UserAccount',
                                        on_delete=django.db.models.deletion.PROTECT)),
                ('submitted_at',    models.DateTimeField()),
                ('tender_total',    models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)),
                ('is_late',         models.BooleanField(default=False)),
                ('disqualified',    models.BooleanField(default=False)),
                ('disq_reason',     models.CharField(max_length=500, blank=True)),
                ('is_awarded',      models.BooleanField(default=False)),
                ('mr_passed',       models.BooleanField(null=True)),
                ('technical_score', models.DecimalField(max_digits=6, decimal_places=3, null=True, blank=True)),
                ('rank',            models.PositiveSmallIntegerField(null=True, blank=True)),
            ],
            options={'ordering': ['rank', '-submitted_at'],
                     'unique_together': {('event', 'submitter_org')}},
        ),

        # ── MandatoryCheck ────────────────────────────────────────────────────
        migrations.CreateModel(
            name='MandatoryCheck',
            fields=[
                ('id',           models.AutoField(primary_key=True)),
                ('submission',   models.ForeignKey('buildwatch.Submission',
                                     on_delete=django.db.models.deletion.CASCADE,
                                     related_name='mr_checks')),
                ('requirement',  models.ForeignKey('buildwatch.MandatoryRequirement',
                                     on_delete=django.db.models.deletion.PROTECT,
                                     null=True, blank=True)),
                ('mr_ref',       models.CharField(max_length=20)),
                ('description',  models.CharField(max_length=500)),
                ('result',       models.CharField(max_length=5)),
                ('notes',        models.TextField(blank=True)),
                ('document_ref', models.CharField(max_length=200, blank=True)),
                ('checked_by',   models.ForeignKey('accounts.UserAccount',
                                     on_delete=django.db.models.deletion.SET_NULL,
                                     null=True, blank=True)),
                ('checked_at',   models.DateTimeField(auto_now_add=True)),
            ],
        ),

        # ── TechnicalScore ────────────────────────────────────────────────────
        migrations.CreateModel(
            name='TechnicalScore',
            fields=[
                ('id',              models.AutoField(primary_key=True)),
                ('submission',      models.ForeignKey('buildwatch.Submission',
                                        on_delete=django.db.models.deletion.CASCADE,
                                        related_name='tech_scores')),
                ('criterion',       models.CharField(max_length=80)),
                ('criterion_label', models.CharField(max_length=200, blank=True)),
                ('weight',          models.DecimalField(max_digits=5, decimal_places=2)),
                ('raw_score',       models.DecimalField(max_digits=5, decimal_places=2)),
                ('weighted_score',  models.DecimalField(max_digits=6, decimal_places=3)),
                ('notes',           models.TextField(blank=True)),
                ('scored_by',       models.ForeignKey('accounts.UserAccount',
                                        on_delete=django.db.models.deletion.SET_NULL,
                                        null=True, blank=True)),
                ('scored_at',       models.DateTimeField(auto_now_add=True)),
            ],
        ),

        # ── SubmissionBillPrice ───────────────────────────────────────────────
        migrations.CreateModel(
            name='SubmissionBillPrice',
            fields=[
                ('id',               models.AutoField(primary_key=True)),
                ('submission',       models.ForeignKey('buildwatch.Submission',
                                         on_delete=django.db.models.deletion.CASCADE,
                                         related_name='bill_prices')),
                ('bill_ref',         models.CharField(max_length=20)),
                ('description',      models.CharField(max_length=255)),
                ('qs_estimate',      models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0'))),
                ('submitted_amount', models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0'))),
                ('approved_amount',  models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0'))),
                ('variance_pct',     models.DecimalField(max_digits=7, decimal_places=3, default=Decimal('0'))),
                ('is_outlier',       models.BooleanField(default=False)),
            ],
        ),

        # ── TenderListing ─────────────────────────────────────────────────────
        migrations.CreateModel(
            name='TenderListing',
            fields=[
                ('id',                      models.AutoField(primary_key=True)),
                ('event',                   models.OneToOneField('buildwatch.EvaluationEvent',
                                                on_delete=django.db.models.deletion.CASCADE,
                                                related_name='listing')),
                ('tender_type',             models.CharField(max_length=20, default='WORKS')),
                ('visibility',              models.CharField(max_length=20, default='PUBLIC')),
                ('funding_source',          models.CharField(max_length=20, default='GOV')),
                ('country',                 models.ForeignKey('buildwatch.Country',
                                                on_delete=django.db.models.deletion.SET_NULL,
                                                null=True, blank=True)),
                ('county_region',           models.CharField(max_length=100, blank=True)),
                ('estimated_value_min',     models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)),
                ('estimated_value_max',     models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)),
                ('currency',                models.CharField(max_length=10, default='KES')),
                ('is_published',            models.BooleanField(default=False)),
                ('published_at',            models.DateTimeField(null=True, blank=True)),
                ('clarification_deadline',  models.DateTimeField(null=True, blank=True)),
                ('site_visit_date',         models.DateTimeField(null=True, blank=True)),
                ('site_visit_location',     models.CharField(max_length=300, blank=True)),
                ('boq_document',            models.FileField(upload_to='tenders/boq/%Y/%m/', null=True, blank=True)),
                ('specification',           models.FileField(upload_to='tenders/spec/%Y/%m/', null=True, blank=True)),
                ('drawings',                models.FileField(upload_to='tenders/drawings/%Y/%m/', null=True, blank=True)),
                ('addendum_count',          models.IntegerField(default=0)),
                ('view_count',              models.IntegerField(default=0)),
                ('registered_bidder_count', models.IntegerField(default=0)),
                ('submission_count',        models.IntegerField(default=0)),
                ('summary',                 models.TextField(blank=True, max_length=500)),
                ('created_at',              models.DateTimeField(auto_now_add=True)),
                ('created_by',              models.ForeignKey('accounts.UserAccount',
                                                on_delete=django.db.models.deletion.PROTECT,
                                                related_name='published_tenders')),
            ],
            options={'ordering': ['-published_at', '-created_at']},
        ),

        # ── TenderInvitation ──────────────────────────────────────────────────
        migrations.CreateModel(
            name='TenderInvitation',
            fields=[
                ('id',                   models.AutoField(primary_key=True)),
                ('tender',               models.ForeignKey('buildwatch.TenderListing',
                                             on_delete=django.db.models.deletion.CASCADE,
                                             related_name='invitations')),
                ('organisation',         models.ForeignKey('accounts.Organization',
                                             on_delete=django.db.models.deletion.PROTECT)),
                ('invited_by',           models.ForeignKey('accounts.UserAccount',
                                             on_delete=django.db.models.deletion.PROTECT)),
                ('invited_at',           models.DateTimeField(auto_now_add=True)),
                ('notification_sent',    models.BooleanField(default=False)),
                ('notification_sent_at', models.DateTimeField(null=True, blank=True)),
                ('viewed_at',            models.DateTimeField(null=True, blank=True)),
                ('accepted',             models.BooleanField(null=True)),
            ],
            options={'unique_together': {('tender', 'organisation')}},
        ),

        # ── TenderAddendum ────────────────────────────────────────────────────
        migrations.CreateModel(
            name='TenderAddendum',
            fields=[
                ('id',             models.AutoField(primary_key=True)),
                ('tender',         models.ForeignKey('buildwatch.TenderListing',
                                       on_delete=django.db.models.deletion.CASCADE,
                                       related_name='addenda')),
                ('addendum_no',    models.PositiveSmallIntegerField()),
                ('subject',        models.CharField(max_length=255)),
                ('content',        models.TextField()),
                ('document',       models.FileField(upload_to='tenders/addenda/%Y/%m/', null=True, blank=True)),
                ('issued_by',      models.ForeignKey('accounts.UserAccount',
                                       on_delete=django.db.models.deletion.PROTECT)),
                ('issued_at',      models.DateTimeField(auto_now_add=True)),
                ('notified_count', models.IntegerField(default=0)),
            ],
            options={'ordering': ['addendum_no'],
                     'unique_together': {('tender', 'addendum_no')}},
        ),

        # ── TenderAlert ───────────────────────────────────────────────────────
        migrations.CreateModel(
            name='TenderAlert',
            fields=[
                ('id',             models.AutoField(primary_key=True)),
                ('organisation',   models.ForeignKey('accounts.Organization',
                                       on_delete=django.db.models.deletion.CASCADE,
                                       related_name='tender_alerts')),
                ('created_by',     models.ForeignKey('accounts.UserAccount',
                                       on_delete=django.db.models.deletion.PROTECT)),
                ('sector',         models.CharField(max_length=50, blank=True)),
                ('tender_type',    models.CharField(max_length=20, blank=True)),
                ('country',        models.ForeignKey('buildwatch.Country',
                                       on_delete=django.db.models.deletion.SET_NULL,
                                       null=True, blank=True)),
                ('county_region',  models.CharField(max_length=100, blank=True)),
                ('value_min',      models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)),
                ('value_max',      models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)),
                ('funding_source', models.CharField(max_length=20, blank=True)),
                ('channel',        models.CharField(max_length=20, default='EMAIL')),
                ('is_active',      models.BooleanField(default=True)),
                ('last_triggered', models.DateTimeField(null=True, blank=True)),
                ('alert_count',    models.IntegerField(default=0)),
                ('created_at',     models.DateTimeField(auto_now_add=True)),
            ],
        ),

        # ── BidderRegistration ────────────────────────────────────────────────
        migrations.CreateModel(
            name='BidderRegistration',
            fields=[
                ('id',                models.AutoField(primary_key=True)),
                ('tender',            models.ForeignKey('buildwatch.TenderListing',
                                          on_delete=django.db.models.deletion.CASCADE,
                                          related_name='bidder_registrations')),
                ('organisation',      models.ForeignKey('accounts.Organization',
                                          on_delete=django.db.models.deletion.PROTECT)),
                ('registered_by',     models.ForeignKey('accounts.UserAccount',
                                          on_delete=django.db.models.deletion.PROTECT)),
                ('registered_at',     models.DateTimeField(auto_now_add=True)),
                ('has_downloaded_boq',models.BooleanField(default=False)),
                ('boq_downloaded_at', models.DateTimeField(null=True, blank=True)),
                ('has_submitted',     models.BooleanField(default=False)),
            ],
            options={'ordering': ['-registered_at'],
                     'unique_together': {('tender', 'organisation')}},
        ),

        # ── BidWorkspace ──────────────────────────────────────────────────────
        migrations.CreateModel(
            name='BidWorkspace',
            fields=[
                ('id',                     models.AutoField(primary_key=True)),
                ('tender',                 models.ForeignKey('buildwatch.TenderListing',
                                               on_delete=django.db.models.deletion.CASCADE,
                                               related_name='workspaces')),
                ('organisation',           models.ForeignKey('accounts.Organization',
                                               on_delete=django.db.models.deletion.PROTECT)),
                ('prepared_by',            models.ForeignKey('accounts.UserAccount',
                                               on_delete=django.db.models.deletion.PROTECT)),
                ('status',                 models.CharField(max_length=20, default='DRAFT')),
                ('self_assessment_passed', models.BooleanField(default=False)),
                ('pricing_complete',       models.BooleanField(default=False)),
                ('total_bid_amount',       models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0'))),
                ('below_market_flag',      models.BooleanField(default=False)),
                ('above_market_flag',      models.BooleanField(default=False)),
                ('started_at',             models.DateTimeField(auto_now_add=True)),
                ('submitted_at',           models.DateTimeField(null=True, blank=True)),
                ('submission',             models.OneToOneField('buildwatch.Submission',
                                               on_delete=django.db.models.deletion.SET_NULL,
                                               null=True, blank=True,
                                               related_name='workspace')),
            ],
            options={'ordering': ['-started_at'],
                     'unique_together': {('tender', 'organisation')}},
        ),

        # ── SelfAssessmentCheck ───────────────────────────────────────────────
        migrations.CreateModel(
            name='SelfAssessmentCheck',
            fields=[
                ('id',                models.AutoField(primary_key=True)),
                ('workspace',         models.ForeignKey('buildwatch.BidWorkspace',
                                          on_delete=django.db.models.deletion.CASCADE,
                                          related_name='self_checks')),
                ('requirement',       models.ForeignKey('buildwatch.MandatoryRequirement',
                                          on_delete=django.db.models.deletion.PROTECT,
                                          null=True, blank=True)),
                ('mr_ref',            models.CharField(max_length=20)),
                ('description',       models.CharField(max_length=500)),
                ('self_result',       models.CharField(max_length=10, default='PENDING')),
                ('document_uploaded', models.BooleanField(default=False)),
                ('document',          models.FileField(upload_to='bids/self_assess/%Y/%m/', null=True, blank=True)),
                ('expiry_date',       models.DateField(null=True, blank=True)),
                ('notes',             models.CharField(max_length=300, blank=True)),
                ('assessed_at',       models.DateTimeField(auto_now=True)),
            ],
        ),

        # ── WorkspaceBillPrice ────────────────────────────────────────────────
        migrations.CreateModel(
            name='WorkspaceBillPrice',
            fields=[
                ('id',               models.AutoField(primary_key=True)),
                ('workspace',        models.ForeignKey('buildwatch.BidWorkspace',
                                         on_delete=django.db.models.deletion.CASCADE,
                                         related_name='bill_prices')),
                ('bill_ref',         models.CharField(max_length=20)),
                ('description',      models.CharField(max_length=255)),
                ('unit',             models.CharField(max_length=30, blank=True)),
                ('quantity',         models.DecimalField(max_digits=12, decimal_places=3, default=Decimal('0'))),
                ('unit_rate',        models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0'))),
                ('amount',           models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0'))),
                ('market_rate_low',  models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)),
                ('market_rate_high', models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)),
                ('is_below_market',  models.BooleanField(default=False)),
                ('is_above_market',  models.BooleanField(default=False)),
            ],
        ),
    ]
