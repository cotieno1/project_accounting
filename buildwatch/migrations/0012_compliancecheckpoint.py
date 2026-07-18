from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("buildwatch", "0011_tenderpreamble"),
        ("accounts", "0051_alter_misccompletionrecord_options_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="ComplianceCheckpoint",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(max_length=40)),
                ("title", models.CharField(max_length=160)),
                ("requirement", models.TextField(blank=True, help_text="What must be confirmed / certified (clause text).")),
                ("category", models.CharField(choices=[("HOLD_POINT", "Hold point - approval required before proceeding"), ("CERTIFICATE", "Certificate / written guarantee"), ("INSPECTION", "Inspection sign-off"), ("SITE_READINESS", "Site readiness (storage, CCTV, equipment, security)")], default="HOLD_POINT", max_length=20)),
                ("responsible_role", models.CharField(choices=[("CONTRACTOR", "Contractor"), ("SITE_MANAGER", "Site Manager / Foreman"), ("ARCHITECT", "Architect"), ("ENGINEER", "Engineer"), ("QS", "Quantity Surveyor"), ("CLIENT", "Client / Employer")], default="CONTRACTOR", help_text="Role accountable for delivering this checkpoint.", max_length=20)),
                ("approver_role", models.CharField(choices=[("CONTRACTOR", "Contractor"), ("SITE_MANAGER", "Site Manager / Foreman"), ("ARCHITECT", "Architect"), ("ENGINEER", "Engineer"), ("QS", "Quantity Surveyor"), ("CLIENT", "Client / Employer")], default="ARCHITECT", help_text="Role that signs off / approves.", max_length=20)),
                ("is_mandatory", models.BooleanField(default=True)),
                ("sort_order", models.PositiveSmallIntegerField(default=0)),
                ("source_page", models.PositiveIntegerField(blank=True, null=True)),
                ("status", models.CharField(choices=[("PENDING", "Pending"), ("SUBMITTED", "Submitted - awaiting sign-off"), ("APPROVED", "Approved / signed off"), ("REJECTED", "Rejected - rework required"), ("NA", "Not applicable")], default="PENDING", max_length=12)),
                ("due_date", models.DateField(blank=True, null=True)),
                ("evidence", models.FileField(blank=True, null=True, upload_to="compliance/evidence/%Y/%m/")),
                ("certificate_ref", models.CharField(blank=True, max_length=100)),
                ("submitted_at", models.DateTimeField(blank=True, null=True)),
                ("signed_off_at", models.DateTimeField(blank=True, null=True)),
                ("notes", models.TextField(blank=True)),
                ("overdue_notified_at", models.DateTimeField(blank=True, help_text="Last time a missed-step alert was sent.", null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("preamble", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="checkpoints", to="buildwatch.tenderpreamble")),
                ("responsible_user", models.ForeignKey(blank=True, help_text="The person taking responsibility for this step.", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="responsible_checkpoints", to="accounts.useraccount")),
                ("signed_off_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="signed_checkpoints", to="accounts.useraccount")),
                ("tender", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="checkpoints", to="buildwatch.tenderlisting")),
            ],
            options={
                "ordering": ["category", "sort_order", "code"],
                "unique_together": {("tender", "code")},
            },
        ),
    ]
