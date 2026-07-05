"""RO draft/confirm workflow: nullable ro_no until confirm, confirmed_at, CONFIRMED status."""

from django.db import migrations, models
from django.utils import timezone


def backfill_confirmed_ros(apps, schema_editor):
    RequisitionOrder = apps.get_model("accounts", "RequisitionOrder")
    for ro in RequisitionOrder.objects.exclude(ro_no__isnull=True).exclude(ro_no=""):
        if ro.status == "DRAFT" or ro.status in ("SUBMITTED", "SIGNED"):
            ro.status = "CONFIRMED"
            ro.confirmed_at = ro.confirmed_at or ro.date_raised or timezone.now()
            ro.save(update_fields=["status", "confirmed_at"])


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0041_budget_review_events"),
    ]

    operations = [
        migrations.AddField(
            model_name="requisitionorder",
            name="confirmed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="requisitionorder",
            name="ro_no",
            field=models.CharField(blank=True, max_length=50, null=True, unique=True),
        ),
        migrations.AlterField(
            model_name="requisitionorder",
            name="status",
            field=models.CharField(
                choices=[
                    ("DRAFT", "Draft"),
                    ("CONFIRMED", "Confirmed"),
                    ("SUBMITTED", "Submitted"),
                    ("SIGNED", "Signed"),
                ],
                default="DRAFT",
                max_length=20,
            ),
        ),
        migrations.RunPython(backfill_confirmed_ros, migrations.RunPython.noop),
    ]