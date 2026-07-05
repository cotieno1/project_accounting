"""Organization onboarding: contractor type, registration status, user terms acceptance."""

from django.db import migrations, models
from django.db.models import deletion
from django.utils import timezone


def backfill_pioneer_onboarding(apps, schema_editor):
    Organization = apps.get_model("accounts", "Organization")
    UserAccount = apps.get_model("accounts", "UserAccount")
    now = timezone.now()
    Organization.objects.filter(org_code="PIONEER").update(
        contractor_type="BUILDING",
        registration_status="ACTIVE",
        terms_accepted_at=now,
    )
    UserAccount.objects.filter(org_terms_accepted_at__isnull=True).update(
        org_terms_accepted_at=now,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0042_ro_confirm_workflow"),
    ]

    operations = [
        migrations.AddField(
            model_name="organization",
            name="contractor_type",
            field=models.CharField(
                choices=[
                    ("BUILDING", "Building contractor"),
                    ("ROADS", "Roads contractor"),
                    ("CONSULTANT", "Consultant"),
                ],
                default="BUILDING",
                help_text="Primary contractor category for onboarding and document defaults.",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="organization",
            name="registration_status",
            field=models.CharField(
                choices=[
                    ("PENDING", "Pending confirmation"),
                    ("ACTIVE", "Active"),
                ],
                default="ACTIVE",
                help_text="Pending until an authorized user accepts subscriber terms.",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="organization",
            name="terms_accepted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="organization",
            name="terms_accepted_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=deletion.SET_NULL,
                related_name="confirmed_organizations",
                to="accounts.useraccount",
            ),
        ),
        migrations.AddField(
            model_name="useraccount",
            name="org_terms_accepted_at",
            field=models.DateTimeField(
                blank=True,
                help_text="When the user accepted platform and subscriber terms of service.",
                null=True,
            ),
        ),
        migrations.RunPython(backfill_pioneer_onboarding, migrations.RunPython.noop),
    ]