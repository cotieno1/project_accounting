from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("buildwatch", "0008_tenderlisting_mr_checklist"),
    ]

    operations = [
        migrations.AddField(
            model_name="tenderboqline",
            name="source_page",
            field=models.PositiveIntegerField(
                blank=True,
                db_index=True,
                help_text=(
                    "1-based PDF page this line was extracted from (PDF-auto ingest)."
                ),
                null=True,
            ),
        ),
    ]
