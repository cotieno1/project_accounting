from django.db import migrations


def forwards(apps, schema_editor):
    Organization = apps.get_model('accounts', 'Organization')
    for org in Organization.objects.filter(org_code='PIONEER'):
        if not (org.organization_type or '').strip():
            org.organization_type = 'CONTRACTOR'
            org.save(update_fields=['organization_type'])


def backwards(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0047_misc_variation_buildwatch_link'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
