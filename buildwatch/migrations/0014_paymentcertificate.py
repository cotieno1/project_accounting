from django.db import migrations, models
import django.db.models.deletion
from decimal import Decimal


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial'),
        ('buildwatch', '0013_tenderconsultant'),
    ]

    operations = [
        migrations.CreateModel(
            name='PaymentCertificate',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('payee_kind', models.CharField(choices=[('CONTRACTOR', 'Contractor'), ('CONSULTANT', 'Consultant')], default='CONTRACTOR', max_length=12)),
                ('payee_name', models.CharField(blank=True, max_length=200)),
                ('cert_type', models.CharField(choices=[('INTERIM', 'Interim payment certificate'), ('ADVANCE', 'Advance / mobilisation'), ('FINAL', 'Final / completion certificate')], default='INTERIM', max_length=10)),
                ('cert_no', models.CharField(blank=True, help_text='Auto: IPC-YYYY-###', max_length=40)),
                ('title', models.CharField(blank=True, max_length=200)),
                ('period_from', models.DateField(blank=True, null=True)),
                ('period_to', models.DateField(blank=True, null=True)),
                ('gross_amount', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=18)),
                ('retention_pct', models.DecimalField(decimal_places=2, default=Decimal('10'), max_digits=5)),
                ('retention_amount', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=18)),
                ('retention_released', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=18)),
                ('net_payable', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=18)),
                ('status', models.CharField(choices=[('DRAFT', 'Draft'), ('CERTIFIED', 'Certified for payment'), ('PAID', 'Paid')], default='DRAFT', max_length=12)),
                ('certified_at', models.DateTimeField(blank=True, null=True)),
                ('paid_reference', models.CharField(blank=True, max_length=100)),
                ('paid_method', models.CharField(blank=True, max_length=20)),
                ('paid_at', models.DateTimeField(blank=True, null=True)),
                ('notes', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('certified_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='certified_payments', to='accounts.useraccount')),
                ('consultant', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='payment_certificates', to='buildwatch.tenderconsultant')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='raised_payments', to='accounts.useraccount')),
                ('payee_org', models.ForeignKey(blank=True, help_text='Contractor company or consultant firm being paid.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='payment_certificates', to='accounts.organization')),
                ('project', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='payment_certificates', to='buildwatch.infraproject')),
                ('tender', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='payment_certificates', to='buildwatch.tenderlisting')),
            ],
            options={
                'ordering': ['-created_at', '-id'],
            },
        ),
    ]
