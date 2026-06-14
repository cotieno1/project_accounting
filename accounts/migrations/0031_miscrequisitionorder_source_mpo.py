from django.db import migrations, models
import django.db.models.deletion


def link_mros_to_mpos(apps, schema_editor):
    MiscRequisitionOrder = apps.get_model("accounts", "MiscRequisitionOrder")
    MiscPurchaseOrder = apps.get_model("accounts", "MiscPurchaseOrder")
    BudgetTransaction = apps.get_model("accounts", "BudgetTransaction")
    for mro in MiscRequisitionOrder.objects.filter(source_mpo_id__isnull=True):
        mro_no = (mro.mro_number or "").strip()
        if not mro_no:
            continue
        txn = (
            BudgetTransaction.objects.filter(
                category="MISC",
                description__icontains=mro_no,
            )
            .order_by("-timestamp")
            .first()
        )
        if not txn or not txn.description:
            continue
        parts = txn.description.split("/")
        if not parts:
            continue
        mpo_ref = parts[0].replace("Ad-hoc RO", "").strip()
        if not mpo_ref:
            continue
        mpo = MiscPurchaseOrder.objects.filter(
            task_id=mro.task_id,
            mpo_number=mpo_ref,
        ).first()
        if mpo and not MiscRequisitionOrder.objects.filter(source_mpo_id=mpo.id).exists():
            mro.source_mpo_id = mpo.id
            mro.save(update_fields=["source_mpo_id"])


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0030_adhoc_officer_voucher_settlement"),
    ]

    operations = [
        migrations.AddField(
            model_name="miscrequisitionorder",
            name="source_mpo",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="committed_mro",
                to="accounts.miscpurchaseorder",
            ),
        ),
        migrations.RunPython(link_mros_to_mpos, migrations.RunPython.noop),
    ]
