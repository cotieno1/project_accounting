from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("buildwatch", "0010_tenderlisting_works_and_conditions"),
    ]

    operations = [
        migrations.CreateModel(
            name="TenderPreamble",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("trade_code", models.CharField(help_text="Short trade key, e.g. EXCAVATION, CONCRETE, WALLING.", max_length=30)),
                ("title", models.CharField(help_text='Trade section heading, e.g. "Excavation and Earthwork".', max_length=120)),
                ("body", models.TextField(help_text="Full clause text (lettered clauses) for this trade.")),
                ("sort_order", models.PositiveSmallIntegerField(default=0)),
                ("source_page", models.PositiveIntegerField(blank=True, help_text="1-based PDF page where this trade section begins.", null=True)),
                ("tender", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="preambles", to="buildwatch.tenderlisting")),
            ],
            options={
                "ordering": ["sort_order", "trade_code"],
                "unique_together": {("tender", "trade_code")},
            },
        ),
    ]
