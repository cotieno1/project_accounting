from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial'),
        ('buildwatch', '0016_projectmilestone'),
    ]

    operations = [
        migrations.CreateModel(
            name='ProjectKickoffSOP',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(default='Pre-commencement SOP & Project Kick-off Agreement', max_length=200)),
                ('status', models.CharField(choices=[('DRAFT', 'Draft'), ('CIRCULATED', 'Circulated - awaiting signatures'), ('SIGNED', 'Signed off by all parties')], default='DRAFT', max_length=12)),
                ('notes', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_sops', to='accounts.useraccount')),
                ('project', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='kickoff_sops', to='buildwatch.infraproject')),
                ('tender', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='kickoff_sops', to='buildwatch.tenderlisting')),
            ],
            options={
                'ordering': ['-created_at', '-id'],
            },
        ),
        migrations.CreateModel(
            name='SOPPrerequisite',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('seq', models.PositiveSmallIntegerField(default=0)),
                ('text', models.CharField(max_length=400)),
                ('responsible', models.CharField(blank=True, max_length=120)),
                ('is_done', models.BooleanField(default=False)),
                ('done_at', models.DateTimeField(blank=True, null=True)),
                ('done_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='completed_prerequisites', to='accounts.useraccount')),
                ('sop', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='prerequisites', to='buildwatch.projectkickoffsop')),
            ],
            options={
                'ordering': ['seq', 'id'],
            },
        ),
        migrations.CreateModel(
            name='SOPPartySignoff',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('role', models.CharField(choices=[('EMPLOYER', 'Employer / Procuring entity'), ('PM_ENGINEER', 'Project Manager / Engineer (PM)'), ('QS', 'Quantity Surveyor'), ('ARCHITECT', 'Architect'), ('CONTRACTOR', 'Contractor'), ('OTHER', 'Other party')], max_length=20)),
                ('party_name', models.CharField(blank=True, max_length=200)),
                ('person_name', models.CharField(blank=True, max_length=150)),
                ('is_required', models.BooleanField(default=True)),
                ('sort_order', models.PositiveSmallIntegerField(default=0)),
                ('signed', models.BooleanField(default=False)),
                ('signed_at', models.DateTimeField(blank=True, null=True)),
                ('signed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='sop_signoffs', to='accounts.useraccount')),
                ('sop', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='signoffs', to='buildwatch.projectkickoffsop')),
            ],
            options={
                'ordering': ['sort_order', 'id'],
                'unique_together': {('sop', 'role')},
            },
        ),
    ]
