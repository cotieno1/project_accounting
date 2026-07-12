from django.apps import AppConfig


class BuildwatchConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "buildwatch"
    label = "buildwatch"
    verbose_name = "BuildWatch — Infrastructure Integrity Platform"

    def ready(self):
        # Signal handlers will be imported here in Sprint 3+
        pass
