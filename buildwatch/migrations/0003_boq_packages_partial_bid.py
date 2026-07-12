from decimal import Decimal

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0049_pioneer_contracting_limited_name'),
        ('buildwatch', '0002_evaluationevent_milestone_placeholder'),
    ]

    operations = [
        migrations.AddField(
            model_name='bidworkspace',
            name='selected_package_codes',
            field=models.JSONField(
                blank=True,
                default=list,
                help_text='TenderBoqPackage.code values selected for this bid',
            ),
        ),
        migrations.AddField(
            model_name='workspacebillprice',
            name='package_code',
            field=models.CharField(
                blank=True,
                default='',
                help_text='TenderBoqPackage.code this line belongs to',
                max_length=20,
            ),
        ),
        migrations.CreateModel(
            name='TenderBoqPackage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(max_length=20)),
                ('title', models.CharField(max_length=120)),
                ('sort_order', models.PositiveSmallIntegerField(default=0)),
                ('tender', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='boq_packages',
                    to='buildwatch.tenderlisting',
                )),
            ],
            options={
                'ordering': ['sort_order', 'code'],
                'unique_together': {('tender', 'code')},
            },
        ),
        migrations.CreateModel(
            name='TenderBoqLine',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('bill_ref', models.CharField(max_length=20)),
                ('description', models.CharField(max_length=255)),
                ('unit', models.CharField(blank=True, default='Sum', max_length=30)),
                ('quantity', models.DecimalField(decimal_places=3, default=Decimal('1'), max_digits=12)),
                ('sort_order', models.PositiveSmallIntegerField(default=0)),
                ('package', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='lines',
                    to='buildwatch.tenderboqpackage',
                )),
            ],
            options={
                'ordering': ['sort_order', 'bill_ref'],
                'unique_together': {('package', 'bill_ref')},
            },
        ),
    ]
