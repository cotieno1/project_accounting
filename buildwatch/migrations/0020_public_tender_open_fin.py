# Hand-written: Public Tender category + Open Tender sub-tasks + Fin Ops resources.
# Intentionally minimal - does not touch Close Tender / ProjectTask schema.

import django.db.models.deletion
from decimal import Decimal
from django.db import migrations, models


def _map_legacy_status(apps, schema_editor):
    WorkSubTask = apps.get_model("buildwatch", "WorkSubTask")
    WorkSubTask.objects.filter(status="APPROVED").update(status="AUTHORIZED")
    WorkSubTask.objects.filter(status="SOURCED").update(status="IN_PROGRESS")


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0001_initial"),
        ("buildwatch", "0019_worksubtask"),
    ]

    operations = [
        migrations.CreateModel(
            name="PublicTenderProfile",
            fields=[
                ("task", models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    primary_key=True,
                    related_name="public_tender_profile",
                    serialize=False,
                    to="accounts.projecttask",
                )),
                ("category", models.CharField(
                    choices=[
                        ("PUBLIC_TENDER", "Public Tender (GOK open)"),
                        ("PPP", "PPP Tender"),
                        ("DONOR", "Donor / DFI Tender"),
                        ("PRIVATE", "Private open tender"),
                    ],
                    default="PUBLIC_TENDER",
                    max_length=20,
                )),
                ("award_letter_ref", models.CharField(blank=True, max_length=120)),
                ("awarded_at", models.DateField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("contractor_org", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="public_tender_profiles",
                    to="accounts.organization",
                )),
                ("tender", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="public_profiles",
                    to="buildwatch.tenderlisting",
                )),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AlterUniqueTogether(
            name="worksubtask",
            unique_together=set(),
        ),
        migrations.AlterField(
            model_name="worksubtask",
            name="milestone",
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="subtasks",
                to="buildwatch.projectmilestone",
            ),
        ),
        migrations.AlterField(
            model_name="worksubtask",
            name="preamble",
            field=models.ForeignKey(
                blank=True, null=True,
                help_text="Governing BOQ preamble trade rules for this category.",
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="subtasks",
                to="buildwatch.tenderpreamble",
            ),
        ),
        migrations.AddField(
            model_name="worksubtask",
            name="profile",
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="subtasks",
                to="buildwatch.publictenderprofile",
            ),
        ),
        migrations.AddField(
            model_name="worksubtask",
            name="kind",
            field=models.CharField(
                choices=[
                    ("BOQ", "Priced BOQ category"),
                    ("INTERNAL", "Internal (financial + non-financial)"),
                ],
                default="BOQ",
                max_length=12,
            ),
        ),
        migrations.AddField(
            model_name="worksubtask",
            name="package_code",
            field=models.CharField(
                blank=True, help_text="TenderBoqPackage.code when kind=BOQ.", max_length=40,
            ),
        ),
        migrations.AddField(
            model_name="worksubtask",
            name="has_financial_impact",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="worksubtask",
            name="has_non_financial_impact",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="worksubtask",
            name="inspected_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="worksubtask",
            name="inspected_by",
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="inspected_subtasks",
                to="accounts.useraccount",
            ),
        ),
        migrations.AddField(
            model_name="worksubtask",
            name="signoff_authority",
            field=models.CharField(
                blank=True, help_text="MoW consultant / local staff / expert who signed off.",
                max_length=200,
            ),
        ),
        migrations.AddField(
            model_name="worksubtask",
            name="certified_products",
            field=models.TextField(
                blank=True,
                help_text="Certified products used (brands / standards / certs).",
            ),
        ),
        migrations.AddField(
            model_name="worksubtask",
            name="proof_notes",
            field=models.TextField(
                blank=True,
                help_text="Proof for audit / examination (DN, photos, tests, certs).",
            ),
        ),
        migrations.AlterField(
            model_name="worksubtask",
            name="status",
            field=models.CharField(
                choices=[
                    ("PLANNED", "Planned"),
                    ("IN_PROGRESS", "In progress"),
                    ("INSPECTION", "Inspection requested"),
                    ("INSPECTED", "Inspected & signed off"),
                    ("AUTHORIZED", "Authorized (Engineer nod)"),
                    ("DONE", "Completed & certified"),
                ],
                default="PLANNED",
                max_length=15,
            ),
        ),
        migrations.AlterModelOptions(
            name="worksubtask",
            options={"ordering": ["kind", "seq", "id"]},
        ),
        migrations.RunPython(_map_legacy_status, migrations.RunPython.noop),
        migrations.CreateModel(
            name="SubTaskResource",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=200)),
                ("resource_kind", models.CharField(
                    choices=[
                        ("MATERIAL", "Material / product"),
                        ("CCTV", "CCTV / surveillance"),
                        ("CLEARING", "Site clearing"),
                        ("SECURITY", "Securing site"),
                        ("EQUIPMENT", "Equipment"),
                        ("EXPLOSIVES", "Explosives"),
                        ("LABOUR", "Labour / resources"),
                        ("OTHER", "Other"),
                    ],
                    default="MATERIAL",
                    max_length=20,
                )),
                ("unit", models.CharField(blank=True, default="No", max_length=30)),
                ("total_qty", models.DecimalField(decimal_places=3, default=Decimal("0"), max_digits=14)),
                ("notes", models.CharField(blank=True, max_length=300)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("subtask", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="resources",
                    to="buildwatch.worksubtask",
                )),
            ],
            options={"ordering": ["resource_kind", "name", "id"]},
        ),
        migrations.CreateModel(
            name="SubTaskResourcePhase",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("phase_index", models.PositiveSmallIntegerField(default=1)),
                ("phase_name", models.CharField(blank=True, max_length=80)),
                ("qty", models.DecimalField(decimal_places=3, default=Decimal("0"), max_digits=14)),
                ("status", models.CharField(
                    choices=[
                        ("PLANNED", "Planned"),
                        ("RO_RAISED", "Internal RO raised"),
                        ("SOURCED", "Sourced (best price)"),
                        ("DELIVERED", "Delivered on site"),
                    ],
                    default="PLANNED",
                    max_length=15,
                )),
                ("ro_ref", models.CharField(
                    blank=True, help_text="Internal RO raised by Onsite Snr Site Engineer.",
                    max_length=80,
                )),
                ("notes", models.CharField(blank=True, max_length=200)),
                ("resource", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="phases",
                    to="buildwatch.subtaskresource",
                )),
            ],
            options={
                "ordering": ["phase_index", "id"],
                "unique_together": {("resource", "phase_index")},
            },
        ),
    ]
