from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0052_organization_telecom_contractor_type"),
    ]

    operations = [
        migrations.AddField(
            model_name="bomitem",
            name="source_bill_ref",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Employer BOQ bill/item reference.",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="bomitem",
            name="source_line_key",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Stable tender-line key used to prevent duplicate imports.",
                max_length=80,
            ),
        ),
        migrations.AddField(
            model_name="bomitem",
            name="source_package_code",
            field=models.CharField(
                blank=True,
                db_index=True,
                default="",
                help_text="Tender BOQ item category / package code.",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="bomitem",
            name="source_tender_ref",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Awarded tender reference when this line was loaded from a priced BOQ.",
                max_length=100,
            ),
        ),
        migrations.AddConstraint(
            model_name="bomitem",
            constraint=models.UniqueConstraint(
                condition=~models.Q(source_line_key=""),
                fields=("header", "source_line_key"),
                name="unique_bom_award_source_line",
            ),
        ),
    ]
