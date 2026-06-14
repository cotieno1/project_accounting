from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0029_seed_pioneer_dev_company"),
    ]

    operations = [
        migrations.AddField(
            model_name="adhocofficerpaymentvoucher",
            name="actual_spent",
            field=models.DecimalField(
                blank=True, decimal_places=2, max_digits=12, null=True
            ),
        ),
        migrations.AddField(
            model_name="adhocofficerpaymentvoucher",
            name="change_returned",
            field=models.DecimalField(
                blank=True, decimal_places=2, max_digits=12, null=True
            ),
        ),
        migrations.AddField(
            model_name="adhocofficerpaymentvoucher",
            name="purchase_receipt_ref",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
        migrations.AddField(
            model_name="adhocofficerpaymentvoucher",
            name="settled_by_name",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="adhocofficerpaymentvoucher",
            name="settled_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
