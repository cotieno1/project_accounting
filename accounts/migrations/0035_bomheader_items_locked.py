from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0034_dedupe_bom_per_task"),
    ]

    operations = [
        migrations.AddField(
            model_name="bomheader",
            name="items_locked",
            field=models.BooleanField(
                default=False,
                help_text="Line items frozen after Snr Site Engineer locks the BOM list.",
            ),
        ),
    ]