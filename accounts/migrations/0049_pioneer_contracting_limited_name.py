from django.db import migrations


def forwards(apps, schema_editor):
    Organization = apps.get_model('accounts', 'Organization')
    for org in Organization.objects.filter(org_code='PIONEER'):
        updates = []
        if (org.name or '').strip() != 'Pioneer Contracting Limited':
            org.name = 'Pioneer Contracting Limited'
            updates.append('name')
        if not (org.organization_type or '').strip():
            org.organization_type = 'CONTRACTOR'
            updates.append('organization_type')
        if updates:
            org.save(update_fields=updates)


def backwards(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0048_pioneer_organization_type_contractor'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
