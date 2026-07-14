from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0049_pioneer_contracting_limited_name"),
    ]

    operations = [
        migrations.AddField(
            model_name="useraccount",
            name="partial_bid_access_ended_at",
            field=models.DateTimeField(
                blank=True,
                help_text=(
                    "When set, login is disabled after partial subcontract BOQ pricing is complete."
                ),
                null=True,
            ),
        ),
    ]
