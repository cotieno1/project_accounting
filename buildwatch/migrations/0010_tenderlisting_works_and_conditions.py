from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("buildwatch", "0009_tenderboqline_source_page"),
    ]

    operations = [
        migrations.AddField(
            model_name="tenderlisting",
            name="works_description",
            field=models.TextField(
                blank=True,
                help_text="Description of the Works shown on the tender detail page.",
            ),
        ),
        migrations.AddField(
            model_name="tenderlisting",
            name="contract_particulars",
            field=models.TextField(
                blank=True,
                help_text=(
                    "Contract particulars / conditions of contract (used instead of "
                    "an MR checklist when this tender publishes conditions)."
                ),
            ),
        ),
    ]
