from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0001_initial"),
        ("buildwatch", "0017_projectkickoffsop"),
    ]

    operations = [
        migrations.AddField(
            model_name="projectkickoffsop",
            name="shared_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="projectkickoffsop",
            name="shared_parties",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="projectkickoffsop",
            name="shared_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="shared_sops",
                to="accounts.useraccount",
            ),
        ),
    ]
