from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0031_miscrequisitionorder_source_mpo"),
    ]

    operations = [
        migrations.AddField(
            model_name="appsettings",
            name="currency_code",
            field=models.CharField(
                default="USD",
                help_text="ISO-style code shown on reports (e.g. USD).",
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="appsettings",
            name="currency_symbol",
            field=models.CharField(
                default="US$",
                help_text="Symbol or prefix shown before amounts (e.g. US$).",
                max_length=10,
            ),
        ),
    ]
