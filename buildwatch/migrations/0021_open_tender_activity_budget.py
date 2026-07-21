# Hand-written: Open Tender activities + activity-based budget lines.

import django.db.models.deletion
from decimal import Decimal
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("buildwatch", "0020_public_tender_open_fin"),
    ]

    operations = [
        migrations.CreateModel(
            name="OpenTenderActivity",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("seq", models.PositiveSmallIntegerField(default=0)),
                ("code", models.CharField(blank=True, help_text="e.g. E07-C", max_length=30)),
                ("name", models.CharField(max_length=255)),
                ("description", models.TextField(blank=True)),
                ("unit", models.CharField(blank=True, help_text="BOQ unit: SM, CM, Lm, Kg", max_length=30)),
                ("measure_unit", models.CharField(
                    blank=True, help_text="Display unit for activity-based budget: m2, m3, m, kg",
                    max_length=20,
                )),
                ("quantity", models.DecimalField(decimal_places=3, default=Decimal("0"), max_digits=14)),
                ("unit_rate", models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=14)),
                ("amount", models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=18)),
                ("location_hint", models.CharField(
                    blank=True, help_text="e.g. Kitchen, Bedroom ensuite, Lift lobby, GF slab",
                    max_length=120,
                )),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("boq_line", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="open_activities",
                    to="buildwatch.tenderboqline",
                )),
                ("subtask", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="activities",
                    to="buildwatch.worksubtask",
                )),
            ],
            options={"ordering": ["subtask_id", "seq", "id"]},
        ),
        migrations.CreateModel(
            name="ActivityBudgetLine",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kind", models.CharField(
                    choices=[
                        ("MATERIAL", "Materials / products"),
                        ("LABOUR", "Labour / resources"),
                        ("EQUIPMENT", "Equipment"),
                        ("INTERNAL", "Internal (non-BOQ / Pioneer)"),
                        ("SUBCONTRACT", "Subcontract"),
                    ],
                    default="MATERIAL",
                    max_length=15,
                )),
                ("name", models.CharField(max_length=200)),
                ("unit", models.CharField(blank=True, max_length=30)),
                ("quantity", models.DecimalField(decimal_places=3, default=Decimal("0"), max_digits=14)),
                ("rate", models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=14)),
                ("amount", models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=18)),
                ("notes", models.CharField(blank=True, max_length=300)),
                ("seq", models.PositiveSmallIntegerField(default=0)),
                ("activity", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="budget_lines",
                    to="buildwatch.opentenderactivity",
                )),
            ],
            options={"ordering": ["seq", "kind", "id"]},
        ),
    ]
