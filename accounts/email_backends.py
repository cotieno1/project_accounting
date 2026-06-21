"""Optional email backends (Resend HTTP API - no extra packages)."""

import json
import urllib.error
import urllib.request

from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend


class ResendEmailBackend(BaseEmailBackend):
    """Send mail via Resend when RESEND_API_KEY is set on Railway or in .env."""

    def send_messages(self, email_messages):
        if not email_messages:
            return 0

        api_key = getattr(settings, "RESEND_API_KEY", "").strip()
        if not api_key:
            if not self.fail_silently:
                raise ValueError("RESEND_API_KEY is not configured")
            return 0

        sent = 0
        for message in email_messages:
            try:
                self._send_one(message, api_key)
                sent += 1
            except Exception:
                if not self.fail_silently:
                    raise
        return sent

    def _send_one(self, message, api_key):
        html_body = None
        text_body = message.body or ""
        for alt, mimetype in getattr(message, "alternatives", []):
            if mimetype == "text/html":
                html_body = alt
                break

        payload = {
            "from": message.from_email,
            "to": list(message.to),
            "subject": message.subject,
            "text": text_body,
        }
        if html_body:
            payload["html"] = html_body
        if message.cc:
            payload["cc"] = list(message.cc)
        if message.reply_to:
            payload["reply_to"] = list(message.reply_to)

        req = urllib.request.Request(
            "https://api.resend.com/emails",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                if resp.status >= 400:
                    raise OSError(resp.read().decode("utf-8", errors="replace"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise OSError(detail or str(exc)) from exc