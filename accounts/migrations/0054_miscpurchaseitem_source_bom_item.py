from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0053_bomitem_award_source"),
    ]

    operations = [
        migrations.AddField(
            model_name="miscpurchaseitem",
            name="source_bom_item",
            field=models.ForeignKey(
                blank=True,
                help_text="Main BOM line this Misc RO item was taken from (known-price buy).",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="misc_purchase_lines",
                to="accounts.bomitem",
            ),
        ),
    ]
