"""Helpers and auth-signal handlers for login incident detection."""
from __future__ import annotations

import ipaddress
import json
import logging
import urllib.error
import urllib.request
from decimal import Decimal, InvalidOperation

from django.contrib.auth.signals import user_logged_in, user_login_failed
from django.core.cache import cache
from django.dispatch import receiver

logger = logging.getLogger("accounts.login_audit")

_GEO_CACHE_TTL = 60 * 60 * 24  # 24h
_GEO_TIMEOUT_SEC = 2.0


def client_ip(request):
    if request is None:
        return None
    forwarded = (request.META.get("HTTP_X_FORWARDED_FOR") or "").strip()
    if forwarded:
        return forwarded.split(",")[0].strip()[:45] or None
    remote = (request.META.get("REMOTE_ADDR") or "").strip()
    return remote[:45] or None


def client_user_agent(request):
    if request is None:
        return ""
    return (request.META.get("HTTP_USER_AGENT") or "")[:400]


def _is_public_ip(ip: str) -> bool:
    try:
        return ipaddress.ip_address(ip).is_global
    except ValueError:
        return False


def _dec(value):
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value)).quantize(Decimal("0.000001"))
    except (InvalidOperation, ValueError, TypeError):
        return None


def resolve_ip_location(ip: str | None) -> dict:
    """Approximate city/region/country from public IP. No browser GPS."""
    empty = {
        "location_label": "",
        "country_code": "",
        "region": "",
        "city": "",
        "latitude": None,
        "longitude": None,
        "geo_source": "ip",
    }
    if not ip:
        return empty
    if not _is_public_ip(ip):
        return {
            **empty,
            "location_label": "Local / private network",
            "geo_source": "ip",
        }

    cache_key = f"login_geo_v1:{ip}"
    cached = cache.get(cache_key)
    if isinstance(cached, dict):
        return cached

    url = (
        f"http://ip-api.com/json/{ip}"
        "?fields=status,message,country,countryCode,regionName,city,lat,lon"
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "BuildWatch-LoginAudit/1.0"})
        with urllib.request.urlopen(req, timeout=_GEO_TIMEOUT_SEC) as resp:
            payload = json.loads(resp.read().decode("utf-8", errors="replace"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        logger.info("login_geo lookup failed ip=%s err=%s", ip, exc)
        result = {**empty, "location_label": "Lookup unavailable"}
        cache.set(cache_key, result, 300)
        return result

    if not isinstance(payload, dict) or payload.get("status") != "success":
        msg = ""
        if isinstance(payload, dict):
            msg = str(payload.get("message") or "")[:80]
        result = {**empty, "location_label": msg or "Lookup unavailable"}
        cache.set(cache_key, result, 300)
        return result

    city = str(payload.get("city") or "").strip()[:100]
    region = str(payload.get("regionName") or "").strip()[:100]
    country = str(payload.get("country") or "").strip()
    country_code = str(payload.get("countryCode") or "").strip()[:8]
    parts = [p for p in (city, region, country) if p]
    result = {
        "location_label": ", ".join(parts)[:200],
        "country_code": country_code,
        "region": region,
        "city": city,
        "latitude": _dec(payload.get("lat")),
        "longitude": _dec(payload.get("lon")),
        "geo_source": "ip",
    }
    cache.set(cache_key, result, _GEO_CACHE_TTL)
    return result


def record_login_event(
    *,
    request=None,
    username="",
    user=None,
    success=False,
    outcome="failed",
    detail="",
):
    from .models import LoginAuditEvent

    ip = client_ip(request)
    ua = client_user_agent(request)
    path = ""
    if request is not None:
        path = (getattr(request, "path", None) or "")[:200]
    username = (username or "").strip()[:150]
    if not username and user is not None:
        username = (getattr(user, "username", None) or "")[:150]

    geo = resolve_ip_location(ip)

    try:
        LoginAuditEvent.objects.create(
            username_attempted=username,
            user=user if getattr(user, "pk", None) else None,
            success=bool(success),
            outcome=outcome,
            ip_address=ip,
            location_label=geo.get("location_label") or "",
            country_code=geo.get("country_code") or "",
            region=geo.get("region") or "",
            city=geo.get("city") or "",
            latitude=geo.get("latitude"),
            longitude=geo.get("longitude"),
            geo_source=geo.get("geo_source") or "ip",
            user_agent=ua,
            path=path,
            detail=(detail or "")[:255],
        )
    except Exception:
        logger.exception("Failed to persist login audit event")
        return

    logger.info(
        "login_audit outcome=%s user=%r ip=%s location=%r path=%s detail=%r",
        outcome,
        username,
        ip,
        geo.get("location_label"),
        path,
        detail,
    )


@receiver(user_logged_in)
def _on_user_logged_in(sender, request, user, **kwargs):
    record_login_event(
        request=request,
        username=getattr(user, "username", "") or "",
        user=user,
        success=True,
        outcome="success",
    )


@receiver(user_login_failed)
def _on_user_login_failed(sender, credentials, request, **kwargs):
    username = ""
    if isinstance(credentials, dict):
        username = credentials.get("username") or credentials.get("email") or ""
    record_login_event(
        request=request,
        username=str(username or ""),
        user=None,
        success=False,
        outcome="failed",
    )