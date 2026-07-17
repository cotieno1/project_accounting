from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("buildwatch", "0007_planned_subcontractor_count"),
    ]

    operations = [
        migrations.AddField(
            model_name="tenderlisting",
            name="mr_checklist",
            field=models.CharField(
                blank=True,
                choices=[
                    ("", "None — no mandatory checklist published yet"),
                    (
                        "KE_ELECTRICAL_RFQ",
                        "Kenya electrical RFQ pack (Isiolo / EPRA / CCTV / solar)",
                    ),
                ],
                default="",
                help_text=(
                    "Which mandatory-requirement pack applies to this tender. "
                    "Blank means none — do not reuse another tender's checklist."
                ),
                max_length=40,
            ),
        ),
    ]
