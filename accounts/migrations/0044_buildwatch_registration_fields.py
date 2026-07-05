"""BuildWatch registration fields on UserAccount + organization_type on Organization."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0043_organization_onboarding"),
    ]

    operations = [
        migrations.AddField(
            model_name="organization",
            name="organization_type",
            field=models.CharField(
                blank=True,
                default="",
                help_text="BuildWatch registration org type (CONTRACTOR, CONSULTANT, GOV_COUNTY, etc.).",
                max_length=30,
            ),
        ),
        migrations.AddField(
            model_name="useraccount",
            name="professional_reg_no",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Professional / contractor licence number (NCA, EBK, etc.).",
                max_length=80,
            ),
        ),
        migrations.AddField(
            model_name="useraccount",
            name="licence_body",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Licensing body code from registration (NCA, EBK, IQSK, etc.).",
                max_length=40,
            ),
        ),
        migrations.AddField(
            model_name="useraccount",
            name="licence_expiry",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="useraccount",
            name="licence_class",
            field=models.CharField(blank=True, default="", max_length=40),
        ),
        migrations.AddField(
            model_name="useraccount",
            name="buildwatch_role",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Primary BuildWatch role selected at registration (QS, ENGINEER, CONTRACTOR, …).",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="useraccount",
            name="registration_pending_review",
            field=models.BooleanField(
                default=False,
                help_text="True until User Admin approves a self-service registration.",
            ),
        ),
    ]