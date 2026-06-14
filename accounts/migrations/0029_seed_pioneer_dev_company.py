from django.db import migrations


def seed_pioneer_dev_company(apps, schema_editor):
    Organization = apps.get_model("accounts", "Organization")
    if Organization.objects.filter(org_code="PIONEER").exists():
        return
    Organization.objects.create(
        org_code="PIONEER",
        name="Pioneer Contactors Co Ltd",
        short_name="Pioneer",
        registered_address="",
        contact_address="TCC Building, 6th floor, Taleex Junction, Mogadishu",
        phone="",
        email="",
        tax_pin="",
        document_tagline="Operations Command",
        is_default=True,
    )


def unseed_pioneer(apps, schema_editor):
    Organization = apps.get_model("accounts", "Organization")
    Organization.objects.filter(org_code="PIONEER").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0028_useraccount_organization"),
    ]

    operations = [
        migrations.RunPython(seed_pioneer_dev_company, unseed_pioneer),
    ]