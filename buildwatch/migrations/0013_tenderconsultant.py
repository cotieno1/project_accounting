from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("buildwatch", "0012_compliancecheckpoint"),
        ("accounts", "0051_alter_misccompletionrecord_options_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="TenderConsultant",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("role", models.CharField(choices=[("PM_ENGINEER", "Project Manager / Engineer (PM)"), ("ARCHITECT", "Architect"), ("QS", "Quantity Surveyor"), ("STRUCTURAL_CIVIL", "Structural / Civil Engineer"), ("ELECTRICAL_MECHANICAL", "Electrical / Mechanical Engineer"), ("SUPERVISION", "Site Supervision"), ("OTHER", "Other consultant")], max_length=30)),
                ("firm_name", models.CharField(blank=True, help_text="Firm / entity name if not a registered org.", max_length=200)),
                ("address", models.CharField(blank=True, max_length=300)),
                ("contact_person", models.CharField(blank=True, max_length=150)),
                ("email", models.EmailField(blank=True, max_length=254)),
                ("phone", models.CharField(blank=True, max_length=40)),
                ("notes", models.CharField(blank=True, max_length=300)),
                ("sort_order", models.PositiveSmallIntegerField(default=0)),
                ("organisation", models.ForeignKey(blank=True, help_text="Registered Consultant organisation in BuildWatch, if any.", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="consultant_appointments", to="accounts.organization")),
                ("tender", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="consultants", to="buildwatch.tenderlisting")),
            ],
            options={
                "ordering": ["sort_order", "role"],
                "unique_together": {("tender", "role")},
            },
        ),
    ]
