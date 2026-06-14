from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0015_remove_lpotransaction_selected_quote_and_more"),
    ]
    operations = [
        migrations.AddField(
            model_name="miscpurchaseitem",
            name="uom",
            field=models.CharField(default="EA", max_length=50),
        ),
    ]