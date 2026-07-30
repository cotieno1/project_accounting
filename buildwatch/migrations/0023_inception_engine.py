# Generated manually for inception engine only (avoid unrelated local model drift).

from decimal import Decimal

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0052_organization_telecom_contractor_type"),
        ("buildwatch", "0022_gate_chain_dependencies"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProjectInception",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("inception_ref", models.CharField(blank=True, help_text="Auto-generated: INC-2026-001", max_length=50, unique=True)),
                ("title", models.CharField(blank=True, max_length=300)),
                ("profile_id", models.CharField(db_index=True, help_text="Programme profile id e.g. buildings.works, ict.telecom_operator", max_length=80)),
                ("sector", models.CharField(choices=[("ROADS", "Roads & Bridges"), ("BUILDINGS", "Buildings"), ("WATER", "Water & Sanitation"), ("ENERGY", "Energy"), ("ICT", "ICT Infrastructure"), ("OTHER", "Other")], default="OTHER", max_length=50)),
                ("county_region", models.CharField(blank=True, max_length=100)),
                ("stage", models.CharField(choices=[("CONCEPT", "1 - Concept: Why this project?"), ("WORKSHOP", "2 - Workshop: Collaborative brief"), ("DOCUMENTED", "3 - Documented: Wish list & budget"), ("SPONSOR_REVIEW", "4 - Sponsor Review"), ("APPROVED", "5 - Approved - proceed to design"), ("DESIGN", "6 - In Design"), ("CANCELLED", "Cancelled")], default="CONCEPT", max_length=20)),
                ("seed_project_ref", models.CharField(blank=True, help_text="Preferred ProjectTask id once approved (optional)", max_length=50)),
                ("workshop_date", models.DateField(blank=True, null=True)),
                ("workshop_venue", models.CharField(blank=True, max_length=300)),
                ("custody_type_id", models.CharField(blank=True, max_length=80)),
                ("custody_status", models.CharField(default="UNKNOWN", max_length=40)),
                ("custody_owner_note", models.CharField(blank=True, max_length=500)),
                ("custody_route_note", models.CharField(blank=True, max_length=500)),
                ("funding_type_id", models.CharField(blank=True, max_length=80)),
                ("funding_status", models.CharField(default="UNFUNDED", max_length=40)),
                ("funding_envelope", models.CharField(blank=True, max_length=80)),
                ("funding_source_note", models.CharField(blank=True, max_length=500)),
                ("activity_log", models.JSONField(blank=True, default=list)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("country", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="buildwatch.country")),
                ("infra_project", models.OneToOneField(blank=True, help_text="Set when inception is approved and project is minted", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="inception", to="buildwatch.infraproject")),
                ("sponsor_contact", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="inception_sponsor_contacts", to="accounts.useraccount")),
                ("sponsor_org", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="sponsored_inceptions", to="accounts.organization")),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="InceptionParticipant",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("role", models.CharField(choices=[("SPONSOR", "Sponsor - project rationale and funding"), ("BUSINESS", "Business - needs, requirements, users"), ("TECHNICAL", "Technical - design viability and budget")], max_length=20)),
                ("technical_discipline", models.CharField(blank=True, help_text="e.g. Quantity Surveyor, Architect, RF Planner", max_length=50)),
                ("invited_at", models.DateTimeField(auto_now_add=True)),
                ("accepted", models.BooleanField(blank=True, null=True)),
                ("accepted_at", models.DateTimeField(blank=True, null=True)),
                ("inception", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="participants", to="buildwatch.projectinception")),
                ("organisation", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="inception_participations", to="accounts.organization")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="inception_participations", to="accounts.useraccount")),
            ],
            options={
                "ordering": ["role", "invited_at"],
                "unique_together": {("inception", "user")},
            },
        ),
        migrations.CreateModel(
            name="InceptionDocument",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("doc_type", models.CharField(choices=[("SKETCH", "Architectural Sketch / Concept Drawing"), ("SITE_PHOTO", "Site Photograph"), ("REFERENCE", "Reference Project"), ("PLANNING", "Planning / Zoning Document"), ("ENVIRONMENTAL", "Environmental Assessment"), ("BUDGET_WORKINGS", "Budget Workings / Cost Data"), ("OTHER", "Other")], default="OTHER", max_length=20)),
                ("title", models.CharField(max_length=255)),
                ("description", models.TextField(blank=True)),
                ("file", models.FileField(blank=True, upload_to="inception/documents/%Y/%m/")),
                ("is_final", models.BooleanField(default=False)),
                ("uploaded_at", models.DateTimeField(auto_now_add=True)),
                ("inception", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="documents", to="buildwatch.projectinception")),
                ("uploaded_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="accounts.useraccount")),
            ],
            options={
                "ordering": ["doc_type", "-uploaded_at"],
            },
        ),
        migrations.CreateModel(
            name="InceptionApproval",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("actioned_by_name", models.CharField(blank=True, max_length=80)),
                ("action", models.CharField(choices=[("APPROVED", "Approved - proceed to design"), ("REVISE", "Revise - return to workshop"), ("CANCELLED", "Cancelled - project not proceeding")], max_length=20)),
                ("comments", models.TextField(blank=True)),
                ("approved_budget", models.DecimalField(blank=True, decimal_places=2, max_digits=15, null=True)),
                ("currency", models.CharField(default="KES", max_length=10)),
                ("minted_project_id", models.CharField(blank=True, max_length=50)),
                ("actioned_at", models.DateTimeField(auto_now_add=True)),
                ("actioned_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="accounts.useraccount")),
                ("inception", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="approvals", to="buildwatch.projectinception")),
            ],
            options={
                "ordering": ["-actioned_at"],
            },
        ),
        migrations.CreateModel(
            name="ConceptBudget",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("currency", models.CharField(default="KES", max_length=10)),
                ("basis_of_estimate", models.TextField(blank=True)),
                ("accuracy", models.CharField(choices=[("PM30", "+/-30% - Order of magnitude"), ("PM20", "+/-20% - Scheme design"), ("PM10", "+/-10% - Detail design"), ("PM5", "+/-5% - Pre-tender estimate")], default="PM30", max_length=5)),
                ("is_approved", models.BooleanField(default=False)),
                ("approved_at", models.DateTimeField(blank=True, null=True)),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("approved_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="approved_concept_budgets", to="accounts.useraccount")),
                ("inception", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="concept_budget", to="buildwatch.projectinception")),
                ("prepared_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="prepared_concept_budgets", to="accounts.useraccount")),
            ],
        ),
        migrations.CreateModel(
            name="WorkshopContribution",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("contribution_type", models.CharField(db_index=True, help_text="Profile or lane code e.g. mandate, SPONSOR_WHY", max_length=40)),
                ("content", models.TextField(blank=True)),
                ("attachments", models.FileField(blank=True, null=True, upload_to="inception/contributions/%Y/%m/")),
                ("is_final", models.BooleanField(default=False)),
                ("updated_by_name", models.CharField(blank=True, max_length=80)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("inception", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="contributions", to="buildwatch.projectinception")),
                ("participant", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="contributions", to="buildwatch.inceptionparticipant")),
            ],
            options={
                "ordering": ["contribution_type", "created_at"],
            },
        ),
        migrations.CreateModel(
            name="ConceptBudgetLine",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(max_length=40)),
                ("label", models.CharField(max_length=200)),
                ("group", models.CharField(blank=True, help_text="e.g. construction, fees, contingency, client", max_length=40)),
                ("amount", models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=15)),
                ("sort_order", models.PositiveSmallIntegerField(default=0)),
                ("budget", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="lines", to="buildwatch.conceptbudget")),
            ],
            options={
                "ordering": ["sort_order", "id"],
                "unique_together": {("budget", "code")},
            },
        ),
        migrations.AddIndex(
            model_name="projectinception",
            index=models.Index(fields=["sponsor_org", "stage"], name="buildwatch__sponsor_00e0fe_idx"),
        ),
        migrations.AddIndex(
            model_name="projectinception",
            index=models.Index(fields=["sponsor_org", "profile_id"], name="buildwatch__sponsor_925160_idx"),
        ),
        migrations.AddConstraint(
            model_name="workshopcontribution",
            constraint=models.UniqueConstraint(fields=("inception", "contribution_type"), name="uniq_inception_contribution_type"),
        ),
    ]
