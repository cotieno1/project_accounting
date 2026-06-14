# Generated manually for ad-hoc officer payment vouchers

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0023_payment_voucher_fields"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AdHocOfficerPaymentVoucher",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("voucher_no", models.CharField(editable=False, max_length=50, unique=True)),
                ("officer_name", models.CharField(max_length=255)),
                ("payment_method", models.CharField(choices=[("CASH", "Cash"), ("MPESA", "M-Pesa")], max_length=10)),
                ("mpesa_reference", models.CharField(blank=True, default="", max_length=100)),
                ("amount", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("gm_authority_name", models.CharField(blank=True, default="", max_length=255)),
                ("prepared_by_name", models.CharField(blank=True, default="", max_length=255)),
                ("payment_notes", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
                ("mpo", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="officer_vouchers", to="accounts.miscpurchaseorder")),
                ("task", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="accounts.projecttask")),
            ],
        ),
        migrations.CreateModel(
            name="AdHocOfficerPaymentVoucherLine",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("qty_purchased", models.DecimalField(decimal_places=2, max_digits=10)),
                ("unit_price", models.DecimalField(decimal_places=2, max_digits=12)),
                ("line_total", models.DecimalField(decimal_places=2, max_digits=12)),
                ("mpo_item", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="officer_purchase_lines", to="accounts.miscpurchaseitem")),
                ("voucher", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="lines", to="accounts.adhocofficerpaymentvoucher")),
            ],
        ),
    ]