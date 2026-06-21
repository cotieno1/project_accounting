from django.db import migrations


def lock_numbered_misc_ros(apps, schema_editor):
    """ROs numbered before lock-on-save fix: treat as locked (view-only)."""
    MiscPurchaseOrder = apps.get_model("accounts", "MiscPurchaseOrder")
    MiscPurchaseOrder.objects.filter(
        is_sourcing=True,
    ).exclude(
        mpo_number__isnull=True,
    ).exclude(
        mpo_number="",
    ).update(is_sourcing=False)


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0036_access_roles_onboarding"),
    ]

    operations = [
        migrations.RunPython(lock_numbered_misc_ros, migrations.RunPython.noop),
    ]
