from django.db import migrations, models
import django.db.models.deletion
from decimal import Decimal


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0001_initial"),
        ("buildwatch", "0018_sop_shared"),
    ]

    operations = [
        migrations.CreateModel(
            name="WorkSubTask",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("seq", models.PositiveSmallIntegerField(default=0)),
                ("code", models.CharField(blank=True, help_text="e.g. A-1", max_length=20)),
                ("name", models.CharField(max_length=200)),
                ("description", models.TextField(blank=True)),
                ("planned_value", models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=18)),
                ("status", models.CharField(default="PLANNED", max_length=15, choices=[
                    ("PLANNED", "Planned"),
                    ("IN_PROGRESS", "In progress"),
                    ("INSPECTION", "Inspection requested"),
                    ("APPROVED", "Inspected & approved"),
                    ("DONE", "Completed & certified"),
                ])),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("approved_at", models.DateTimeField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("certificate_ref", models.CharField(blank=True, max_length=60)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("approved_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="approved_subtasks", to="accounts.useraccount")),
                ("started_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="started_subtasks", to="accounts.useraccount")),
                ("completed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="completed_subtasks", to="accounts.useraccount")),
                ("checkpoint", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="subtasks", to="buildwatch.compliancecheckpoint", help_text="Inspection / hold-point / certificate gate for this sub-task.")),
                ("milestone", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="subtasks", to="buildwatch.projectmilestone")),
                ("preamble", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="subtasks", to="buildwatch.tenderpreamble", help_text="Governing BOQ trade preamble (measurement / workmanship).")),
                ("project", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="work_subtasks", to="buildwatch.infraproject")),
                ("tender", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="work_subtasks", to="buildwatch.tenderlisting")),
            ],
            options={
                "ordering": ["milestone_id", "seq", "id"],
                "unique_together": {("milestone", "seq")},
            },
        ),
    ]
