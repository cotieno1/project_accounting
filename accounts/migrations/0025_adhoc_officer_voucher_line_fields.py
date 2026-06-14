from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0024_adhoc_officer_payment_voucher"),
    ]

    operations = [
        migrations.AddField(
            model_name="adhocofficerpaymentvoucherline",
            name="line_no",
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="adhocofficerpaymentvoucherline",
            name="qty_balance",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
        ),
    ]