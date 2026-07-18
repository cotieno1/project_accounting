from django.db import migrations, models
import django.db.models.deletion
from decimal import Decimal


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial'),
        ('buildwatch', '0015_paymentcertificate_ro_pv'),
    ]

    operations = [
        migrations.CreateModel(
            name='ProjectMilestone',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('phase_index', models.PositiveSmallIntegerField(default=0, help_text='Matches the BOQ programme phase (0=mobilisation ... 9=handover).')),
                ('seq', models.PositiveSmallIntegerField(default=0)),
                ('name', models.CharField(max_length=200)),
                ('description', models.CharField(blank=True, max_length=300)),
                ('planned_start_week', models.PositiveSmallIntegerField(default=1)),
                ('duration_weeks', models.PositiveSmallIntegerField(default=2)),
                ('planned_start_date', models.DateField(blank=True, null=True)),
                ('planned_end_date', models.DateField(blank=True, null=True)),
                ('value_amount', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=18)),
                ('value_pct', models.DecimalField(decimal_places=3, default=Decimal('0'), max_digits=6)),
                ('status', models.CharField(choices=[('PENDING', 'Not started'), ('IN_PROGRESS', 'In progress'), ('DELIVERED', 'Delivered / signed off')], default='PENDING', max_length=15)),
                ('delivered_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('delivered_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='delivered_milestones', to='accounts.useraccount')),
                ('project', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='milestones', to='buildwatch.infraproject')),
                ('tender', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='milestones', to='buildwatch.tenderlisting')),
            ],
            options={
                'ordering': ['seq', 'phase_index', 'id'],
                'unique_together': {('project', 'phase_index')},
            },
        ),
        migrations.AddField(
            model_name='paymentcertificate',
            name='milestone',
            field=models.ForeignKey(blank=True, help_text='Delivery/payment stage this certificate is claimed against.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='certificates', to='buildwatch.projectmilestone'),
        ),
    ]
