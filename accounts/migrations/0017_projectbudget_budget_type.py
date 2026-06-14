from django.db import migrations, models


def backfill_budget_type(apps, schema_editor):
    ProjectBudget = apps.get_model("accounts", "ProjectBudget")
    MiscPurchaseOrder = apps.get_model("accounts", "MiscPurchaseOrder")
    MiscRequisitionOrder = apps.get_model("accounts", "MiscRequisitionOrder")
    LPOTransaction = apps.get_model("accounts", "LPOTransaction")

    for budget in ProjectBudget.objects.all():
        if not budget.task_id:
            budget.budget_type = "RFQ_LPO"
            budget.save(update_fields=["budget_type"])
            continue
        task_id = budget.task_id
        has_adhoc = (
            MiscPurchaseOrder.objects.filter(task_id=task_id).exists()
            or MiscRequisitionOrder.objects.filter(task_id=task_id).exists()
        )
        has_lpo = LPOTransaction.objects.filter(project_task_id=task_id).exists()
        if has_adhoc and not has_lpo:
            budget.budget_type = "ADHOC_MISC"
        elif "Ad-Hoc" in (budget.budget_label or ""):
            budget.budget_type = "ADHOC_MISC"
        else:
            budget.budget_type = "RFQ_LPO"
        budget.save(update_fields=["budget_type"])


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0016_miscpurchaseitem_uom"),
    ]

    operations = [
        migrations.AddField(
            model_name="projectbudget",
            name="budget_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("RFQ_LPO", "Task Budget (RFQ / LPO)"),
                    ("ADHOC_MISC", "Ad-Hoc / Misc Budget"),
                ],
                default="RFQ_LPO",
                max_length=20,
            ),
        ),
        migrations.RunPython(backfill_budget_type, migrations.RunPython.noop),
    ]
