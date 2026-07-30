# Generated manually for project work plan (rollout / financing / BOM).

from decimal import Decimal

import django.db.models.deletion
from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ("buildwatch", "0023_inception_engine"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProjectWorkPlan",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("profile_id", models.CharField(blank=True, max_length=80)),
                ("title", models.CharField(blank=True, max_length=300)),
                ("status", models.CharField(choices=[("DRAFT", "Draft"), ("APPROVED", "Approved"), ("ACTIVE", "Active rollout"), ("CLOSED", "Closed")], default="DRAFT", max_length=20)),
                ("currency", models.CharField(default="KES", max_length=10)),
                ("total_envelope", models.DecimalField(decimal_places=2, default=Decimal("0"), help_text="Strategic financing envelope for the rollout programme", max_digits=18)),
                ("strategy_note", models.TextField(blank=True, help_text="How waves are staggered and why (coverage, cash, logistics)")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("inception", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="work_plans", to="buildwatch.projectinception")),
                ("infra_project", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="work_plan", to="buildwatch.infraproject")),
            ],
            options={
                "ordering": ["-updated_at"],
            },
        ),
        migrations.CreateModel(
            name="WorkPlanPhase",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(max_length=40)),
                ("label", models.CharField(max_length=200)),
                ("kind", models.CharField(choices=[("TEST", "Test / proof"), ("PILOT", "Pilot"), ("WAVE", "Rollout wave"), ("INTEGRATION", "Integration / acceptance"), ("COMMISSIONING", "Commissioning"), ("HANDOVER", "Handover"), ("OTHER", "Other")], default="WAVE", max_length=20)),
                ("sort_order", models.PositiveSmallIntegerField(default=0)),
                ("objective", models.TextField(blank=True)),
                ("exit_criteria", models.TextField(blank=True, help_text="What must be true before the next phase starts")),
                ("planned_start", models.DateField(blank=True, null=True)),
                ("planned_end", models.DateField(blank=True, null=True)),
                ("site_or_scope", models.CharField(blank=True, help_text="e.g. 10 pilot BTS sites / Juba corridor", max_length=300)),
                ("financing_pct", models.DecimalField(decimal_places=2, default=Decimal("0"), help_text="% of programme envelope released for this phase", max_digits=6)),
                ("financing_amount", models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=18)),
                ("financing_trigger", models.CharField(blank=True, help_text="e.g. Pilot acceptance signed / Wave-1 RF complete", max_length=200)),
                ("is_complete", models.BooleanField(default=False)),
                ("plan", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="phases", to="buildwatch.projectworkplan")),
            ],
            options={
                "ordering": ["sort_order", "id"],
                "unique_together": {("plan", "code")},
            },
        ),
        migrations.CreateModel(
            name="WorkPlanBomLine",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("item_code", models.CharField(blank=True, max_length=50)),
                ("description", models.CharField(max_length=300)),
                ("unit", models.CharField(default="Nr", max_length=20)),
                ("quantity", models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=14)),
                ("unit_cost", models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=18)),
                ("sort_order", models.PositiveSmallIntegerField(default=0)),
                ("notes", models.CharField(blank=True, max_length=300)),
                ("phase", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="bom_lines", to="buildwatch.workplanphase")),
                ("plan", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="bom_lines", to="buildwatch.projectworkplan")),
            ],
            options={
                "ordering": ["sort_order", "id"],
            },
        ),
        migrations.CreateModel(
            name="WorkPlanActivity",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("at", models.DateTimeField(default=django.utils.timezone.now)),
                ("who", models.CharField(blank=True, max_length=80)),
                ("text", models.CharField(max_length=400)),
                ("plan", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="activities", to="buildwatch.projectworkplan")),
            ],
            options={
                "ordering": ["-at"],
            },
        ),
    ]
