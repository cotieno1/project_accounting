from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0039_useraccount_professional_fields'),
        ('buildwatch', '0001_initial'),   # BuildWatch must be migrated first
    ]

    operations = [

        # ── Fields added to existing MiscPurchaseOrder ───────────────────────
        migrations.AddField(
            model_name='MiscPurchaseOrder',
            name='infra_project',
            field=models.ForeignKey(
                'buildwatch.InfraProject',
                on_delete=django.db.models.deletion.SET_NULL,
                null=True,
                blank=True,
                related_name='misc_variations',
                help_text='BuildWatch project this misc purchase belongs to (if any).',
            ),
        ),
        migrations.AddField(
            model_name='MiscPurchaseOrder',
            name='variation_ref',
            field=models.CharField(
                max_length=20,
                blank=True,
                default='',
                help_text='Auto-assigned: MV-001, MV-002 … within the project.',
            ),
        ),
        migrations.AddField(
            model_name='MiscPurchaseOrder',
            name='scope_description',
            field=models.TextField(
                blank=True,
                default='',
                help_text='Plain-English description of the physical work to be done.',
            ),
        ),
        migrations.AddField(
            model_name='MiscPurchaseOrder',
            name='budget_ceiling',
            field=models.DecimalField(
                max_digits=15,
                decimal_places=2,
                null=True,
                blank=True,
                help_text='CEO-approved spending ceiling. Locked after approval.',
            ),
        ),
        migrations.AddField(
            model_name='MiscPurchaseOrder',
            name='ceiling_locked',
            field=models.BooleanField(
                default=False,
                help_text='True after CEO approves. total_amount cannot exceed budget_ceiling.',
            ),
        ),
        migrations.AddField(
            model_name='MiscPurchaseOrder',
            name='variation_status',
            field=models.CharField(
                max_length=20,
                default='DRAFT',
                choices=[
                    ('DRAFT',           'Draft — RO being prepared'),
                    ('SUBMITTED',       'Submitted to CEO for approval'),
                    ('APPROVED',        'CEO Approved — funds being released'),
                    ('ACTIVE',          'Active — officer executing work'),
                    ('PENDING_SIGNOFF', 'Pending Engineer Sign-off'),
                    ('RECONCILED',      'Reconciled — GL closed'),
                    ('CANCELLED',       'Cancelled'),
                ],
            ),
        ),

        # ── New MiscCompletionRecord table ───────────────────────────────────
        migrations.CreateModel(
            name='MiscCompletionRecord',
            fields=[
                ('id', models.AutoField(primary_key=True)),
                ('mpo', models.OneToOneField(
                    'accounts.MiscPurchaseOrder',
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='completion_record',
                )),
                ('completed_by', models.ForeignKey(
                    'accounts.UserAccount',
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='misc_completions_signed',
                )),
                ('scope_achieved', models.TextField(
                    help_text='Description of what was physically completed.',
                )),
                ('photo_1', models.ImageField(
                    upload_to='misc_completions/%Y/%m/',
                    help_text='Required: photo of completed work.',
                )),
                ('photo_2', models.ImageField(
                    upload_to='misc_completions/%Y/%m/',
                    null=True,
                    blank=True,
                )),
                ('photo_3', models.ImageField(
                    upload_to='misc_completions/%Y/%m/',
                    null=True,
                    blank=True,
                )),
                ('actual_cost', models.DecimalField(
                    max_digits=15,
                    decimal_places=2,
                    help_text='Total actual spend from receipts.',
                )),
                ('variance_amount', models.DecimalField(
                    max_digits=15,
                    decimal_places=2,
                    default=0,
                    help_text='actual_cost minus budget_ceiling. Negative = underspend.',
                )),
                ('quality_notes', models.TextField(blank=True, default='')),
                ('signed_off_at', models.DateTimeField(auto_now_add=True)),
            ],
        ),

        # ── New MiscVariation table ──────────────────────────────────────────
        migrations.CreateModel(
            name='MiscVariation',
            fields=[
                ('id', models.AutoField(primary_key=True)),
                ('mpo', models.OneToOneField(
                    'accounts.MiscPurchaseOrder',
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='variation_record',
                )),
                ('project', models.ForeignKey(
                    'buildwatch.InfraProject',
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='misc_variation_records',
                )),
                ('variation_type', models.CharField(
                    max_length=20,
                    default='MISC_SELF_EXECUTE',
                    editable=False,
                )),
                ('ref', models.CharField(max_length=20)),
                ('description', models.CharField(max_length=500)),
                ('approved_value', models.DecimalField(
                    max_digits=15, decimal_places=2, default=0,
                )),
                ('actual_value', models.DecimalField(
                    max_digits=15, decimal_places=2, default=0,
                )),
                ('status', models.CharField(
                    max_length=15,
                    default='DRAFT',
                    choices=[
                        ('DRAFT',       'Draft'),
                        ('APPROVED',    'CEO Approved'),
                        ('ACTIVE',      'Active'),
                        ('RECONCILED',  'Reconciled'),
                        ('CANCELLED',   'Cancelled'),
                    ],
                )),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('reconciled_at', models.DateTimeField(null=True, blank=True)),
            ],
            options={'ordering': ['ref']},
        ),
    ]
