from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial'),
        ('buildwatch', '0014_paymentcertificate'),
    ]

    operations = [
        migrations.AlterField(
            model_name='paymentcertificate',
            name='status',
            field=models.CharField(
                choices=[
                    ('DRAFT', 'Draft'),
                    ('CERTIFIED', 'Certified for payment'),
                    ('REQUISITIONED', 'Requisition order raised'),
                    ('PAID', 'Payment order raised / funds transferred'),
                ],
                default='DRAFT', max_length=15,
            ),
        ),
        migrations.AlterField(
            model_name='paymentcertificate',
            name='paid_reference',
            field=models.CharField(blank=True, help_text='Bank/M-Pesa/cheque transfer reference', max_length=100),
        ),
        migrations.AddField(
            model_name='paymentcertificate',
            name='ro_no',
            field=models.CharField(blank=True, help_text='Auto: RO-YYYY-###', max_length=40),
        ),
        migrations.AddField(
            model_name='paymentcertificate',
            name='ro_raised_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='paymentcertificate',
            name='ro_raised_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='requisitioned_payments', to='accounts.useraccount'),
        ),
        migrations.AddField(
            model_name='paymentcertificate',
            name='pv_no',
            field=models.CharField(blank=True, help_text='Auto: PV-YYYY-###', max_length=40),
        ),
    ]
