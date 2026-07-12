from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("buildwatch", "0003_boq_packages_partial_bid"),
    ]

    operations = [
        migrations.AddField(
            model_name="tenderlisting",
            name="boq_input_mode",
            field=models.CharField(
                choices=[
                    ("HARDWIRED", "A - Hardwired BOQ (curated seed)"),
                    ("PDF_AUTO", "B - Automated from RFQ/BOQ PDF"),
                ],
                default="HARDWIRED",
                help_text="Which BOQ source feeds the bid workspace form",
                max_length=20,
            ),
        ),
    ]
