from django.shortcuts import redirect
from django.urls import reverse


class MustChangePasswordMiddleware:
    EXEMPT_PREFIXES = (
        "/logout/",
        "/login/",
        "/accounts/set-password/",
        "/accounts/resend-onboarding/",
        "/health/",
        "/static/",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and not request.user.is_superuser:
            path = request.path
            if not any(path.startswith(p) for p in self.EXEMPT_PREFIXES):
                try:
                    if request.user.useraccount.must_change_password:
                        return redirect(reverse("password_change_required"))
                except Exception:
                    pass
        return self.get_response(request)