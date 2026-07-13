# Generated manually for SubcontractArrangement

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0049_pioneer_contracting_limited_name"),
        ("buildwatch", "0004_boq_input_mode"),
    ]

    operations = [
        migrations.CreateModel(
            name="SubcontractArrangement",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("arrangement_type", models.CharField(choices=[("DOMESTIC", "Domestic sub-contractor"), ("NOMINATED", "Nominated sub-contractor")], default="DOMESTIC", max_length=20)),
                ("status", models.CharField(choices=[("DRAFT", "Draft"), ("INVITED", "Invitation sent"), ("ACCEPTED", "Sub-contractor accepted"), ("AGREEMENT_UPLOADED", "Agreement uploaded"), ("SHARED_WITH_SPONSOR", "Shared with sponsor"), ("CANCELLED", "Cancelled")], default="DRAFT", max_length=30)),
                ("package_codes", models.JSONField(blank=True, default=list, help_text="TenderBoqPackage.code values covered by this subcontract.")),
                ("sub_company_name", models.CharField(max_length=200)),
                ("sub_contact_name", models.CharField(blank=True, max_length=120)),
                ("sub_email", models.EmailField(max_length=254)),
                ("sub_phone", models.CharField(blank=True, max_length=40)),
                ("notes", models.TextField(blank=True, help_text="Scope notes for the sub (packages, hold-points, etc.).")),
                ("payment_via_main", models.BooleanField(default=True, help_text="RFQ default: payment through main contractor certificates.")),
                ("approval_by_consultant", models.BooleanField(default=False, help_text="Nominated path: work inspected/approved by owner's consultant before valuation.")),
                ("invite_token", models.CharField(db_index=True, max_length=64, unique=True)),
                ("invited_at", models.DateTimeField(blank=True, null=True)),
                ("invite_email_sent", models.BooleanField(default=False)),
                ("invite_email_error", models.CharField(blank=True, max_length=400)),
                ("accepted_at", models.DateTimeField(blank=True, null=True)),
                ("agreement_file", models.FileField(blank=True, help_text="Signed domestic / nominated sub-contractor agreement (MR14).", null=True, upload_to="tenders/subcontracts/%Y/%m/")),
                ("agreement_uploaded_at", models.DateTimeField(blank=True, null=True)),
                ("shared_with_sponsor_at", models.DateTimeField(blank=True, null=True)),
                ("sponsor_notified", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("invited_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="subcontract_invites_sent", to="accounts.useraccount")),
                ("main_organisation", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="main_subcontracts", to="accounts.organization")),
                ("sub_organisation", models.ForeignKey(blank=True, help_text="Filled when the invitee is linked to an existing BuildWatch org.", null=True, on_delete=django.db.models.deletion.PROTECT, related_name="as_subcontracts", to="accounts.organization")),
                ("tender", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="subcontracts", to="buildwatch.tenderlisting")),
                ("workspace", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="subcontracts", to="buildwatch.bidworkspace")),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
    ]
