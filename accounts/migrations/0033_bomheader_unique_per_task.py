from django.db import migrations, models
from django.db.models import Count, Q
import re


def _next_bom_id(BOMHeader):
    last_bom = BOMHeader.objects.exclude(bom_id="").order_by("id").last()
    if not last_bom or not (last_bom.bom_id or "").strip():
        return "BOM-100"
    match = re.search(r"(\d+)", last_bom.bom_id)
    if match:
        return f"BOM-{int(match.group(1)) + 1}"
    return "BOM-100"


def prepare_bom_headers(apps, schema_editor):
    BOMHeader = apps.get_model("accounts", "BOMHeader")

    for bom in BOMHeader.objects.filter(Q(bom_id__isnull=True) | Q(bom_id="")):
        bom.bom_id = _next_bom_id(BOMHeader)
        bom.save(update_fields=["bom_id"])

    task_ids = BOMHeader.objects.values_list("task_id", flat=True).distinct()
    for task_id in task_ids:
        boms = list(
            BOMHeader.objects.filter(task_id=task_id)
            .annotate(item_count=Count("items"))
            .order_by("-item_count", "-id")
        )
        if len(boms) <= 1:
            continue
        for dup in boms[1:]:
            dup.delete()


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0032_appsettings_currency"),
    ]

    operations = [
        migrations.RunPython(prepare_bom_headers, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="bomheader",
            constraint=models.UniqueConstraint(
                fields=["task"], name="unique_bom_per_task"
            ),
        ),
    ]
