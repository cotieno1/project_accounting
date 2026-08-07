from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'accounts'

    def ready(self):
        # Register login success/fail audit signal handlers.
        from . import login_audit  # noqa: F401
