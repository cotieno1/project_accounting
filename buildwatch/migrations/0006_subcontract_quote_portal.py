from decimal import Decimal

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0049_pioneer_contracting_limited_name"),
        ("buildwatch", "0005_subcontract_arrangement"),
    ]

    operations = [
        migrations.AddField(
            model_name="subcontractarrangement",
            name="award_note_sent",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="subcontractarrangement",
            name="award_noted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="subcontractarrangement",
            name="included_in_main_bid_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="subcontractarrangement",
            name="quote_acknowledged_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="subcontractarrangement",
            name="quote_acknowledged_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="subcontract_quotes_acked",
                to="accounts.useraccount",
            ),
        ),
        migrations.AddField(
            model_name="subcontractarrangement",
            name="quote_status",
            field=models.CharField(
                blank=True,
                choices=[
                    ("", "No quote yet"),
                    ("QUOTE_DRAFT", "Pricing in progress"),
                    ("QUOTE_SUBMITTED", "Quote submitted to main"),
                    ("QUOTE_ACKNOWLEDGED", "Acknowledged by main contractor"),
                    ("QUOTE_INCLUDED", "Included in main bid package"),
                    ("AWARD_NOTED", "Main awarded — execution phase note sent"),
                ],
                default="",
                max_length=30,
            ),
        ),
        migrations.AddField(
            model_name="subcontractarrangement",
            name="quote_submitted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="subcontractarrangement",
            name="quote_total",
            field=models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=15),
        ),
        migrations.CreateModel(
            name="SubcontractQuoteLine",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("package_code", models.CharField(blank=True, default="", max_length=20)),
                ("bill_ref", models.CharField(max_length=20)),
                ("description", models.CharField(max_length=255)),
                ("unit", models.CharField(blank=True, max_length=30)),
                ("quantity", models.DecimalField(decimal_places=3, default=Decimal("0"), max_digits=12)),
                ("unit_rate", models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=12)),
                ("amount", models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=15)),
                (
                    "arrangement",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="quote_lines",
                        to="buildwatch.subcontractarrangement",
                    ),
                ),
            ],
            options={
                "ordering": ["package_code", "bill_ref"],
                "unique_together": {("arrangement", "bill_ref")},
            },
        ),
    ]
