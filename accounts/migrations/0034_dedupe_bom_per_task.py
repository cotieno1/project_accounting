from django.db import migrations
from django.db.models import Count, Q
import re


def _next_bom_id(BOMHeader):
    max_num = 99
    for bom_id in BOMHeader.objects.values_list("bom_id", flat=True):
        match = re.search(r"(\d+)", bom_id or "")
        if match:
            max_num = max(max_num, int(match.group(1)))
    return f"BOM-{max_num + 1}"


def dedupe_all_task_boms(apps, schema_editor):
    BOMHeader = apps.get_model("accounts", "BOMHeader")
    BOMItem = apps.get_model("accounts", "BOMItem")

    for bom in BOMHeader.objects.filter(Q(bom_id__isnull=True) | Q(bom_id="")):
        bom.bom_id = _next_bom_id(BOMHeader)
        bom.save(update_fields=["bom_id"])

    task_ids = BOMHeader.objects.values_list("task_id", flat=True).distinct()
    for task_id in task_ids:
        boms = list(
            BOMHeader.objects.filter(task_id=task_id)
            .annotate(item_count=Count("items"))
            .order_by("-item_count", "-created_at", "-id")
        )
        if len(boms) <= 1:
            continue
        keep = boms[0]
        for dup in boms[1:]:
            for item in BOMItem.objects.filter(header_id=dup.id):
                item.header_id = keep.id
                item.save(update_fields=["header_id"])
            dup.delete()


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0033_bomheader_unique_per_task"),
    ]

    operations = [
        migrations.RunPython(dedupe_all_task_boms, migrations.RunPython.noop),
    ]
