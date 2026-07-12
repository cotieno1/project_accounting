from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('buildwatch', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='evaluationevent',
            name='milestone_id_legacy',
            field=models.PositiveIntegerField(
                blank=True,
                help_text='Reserved for execution.Milestone PK (Sprint 3+)',
                null=True,
            ),
        ),
    ]
