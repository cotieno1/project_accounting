from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0037_lock_numbered_misc_ros"),
    ]

    operations = [
        migrations.AddField(
            model_name="useraccount",
            name="onboarding_email_sent_at",
            field=models.DateTimeField(
                blank=True,
                help_text="When the onboarding set-password email was last sent successfully.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="useraccount",
            name="onboarding_email_last_error",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Last onboarding email failure message, if any.",
                max_length=255,
            ),
        ),
    ]
