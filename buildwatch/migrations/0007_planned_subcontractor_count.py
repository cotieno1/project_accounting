from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("buildwatch", "0006_subcontract_quote_portal"),
    ]

    operations = [
        migrations.AddField(
            model_name="bidworkspace",
            name="planned_subcontractor_count",
            field=models.PositiveSmallIntegerField(
                blank=True,
                help_text=(
                    "How many sub-contractors this main contractor needs on this bid "
                    "(0 = none / MR14 N/A). Invite form locks when active invites reach N."
                ),
                null=True,
            ),
        ),
    ]
