# Gate chain: CERTIFIED / PAYABLE / PAID + ActivityDependency (FS).

import django.db.models.deletion
from django.db import migrations, models


def _remap_done(apps, schema_editor):
    WorkSubTask = apps.get_model("buildwatch", "WorkSubTask")
    WorkSubTask.objects.filter(status="DONE").update(status="PAID")
    # Older works-execution rows used APPROVED for engineer nod.
    WorkSubTask.objects.filter(status="APPROVED").update(status="AUTHORIZED")


class Migration(migrations.Migration):

    dependencies = [
        ("buildwatch", "0021_open_tender_activity_budget"),
    ]

    operations = [
        migrations.AlterField(
            model_name="worksubtask",
            name="status",
            field=models.CharField(
                choices=[
                    ("PLANNED", "Planned"),
                    ("IN_PROGRESS", "In progress (work)"),
                    ("INSPECTION", "Inspection requested"),
                    ("INSPECTED", "Inspected (QA)"),
                    ("CERTIFIED", "Certified (cert + products + proof)"),
                    ("AUTHORIZED", "Authorized (Engineer nod)"),
                    ("PAYABLE", "Payable (ready for RO/PV)"),
                    ("PAID", "Paid (PV / funds transferred)"),
                ],
                default="PLANNED",
                max_length=15,
            ),
        ),
        migrations.RunPython(_remap_done, migrations.RunPython.noop),
        migrations.CreateModel(
            name="ActivityDependency",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("dep_type", models.CharField(
                    choices=[("FS", "Finish-to-start (must wait)")],
                    default="FS",
                    max_length=4,
                )),
                ("required_status", models.CharField(
                    default="AUTHORIZED",
                    help_text="Predecessor must reach this gate before successor may start.",
                    max_length=15,
                )),
                ("note", models.CharField(blank=True, max_length=200)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("predecessor_subtask", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="successor_links",
                    to="buildwatch.worksubtask",
                )),
                ("profile", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="activity_dependencies",
                    to="buildwatch.publictenderprofile",
                )),
                ("successor_subtask", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="predecessor_links",
                    to="buildwatch.worksubtask",
                )),
            ],
            options={
                "ordering": ["id"],
                "unique_together": {("predecessor_subtask", "successor_subtask")},
            },
        ),
    ]
