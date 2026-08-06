
import hashlib
import re
from datetime import timedelta
from urllib.parse import urlparse

from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import LimitationSecurite


DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$",
    re.IGNORECASE,
)
SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,100}$")
PHONE_RE = re.compile(r"^[0-9+(). /-]{6,30}$")


def client_ip(request):
    forwarded = (request.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
    return (
        request.headers.get("Fly-Client-IP")
        or request.headers.get("CF-Connecting-IP")
        or forwarded
        or request.META.get("REMOTE_ADDR")
        or "unknown"
    )


def normalize_domain(value):
    raw = (value or "").strip().lower()
    if not raw:
        return ""
    parsed = urlparse(raw if "://" in raw else f"//{raw}")
    host = (parsed.hostname or "").lower().rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    if not DOMAIN_RE.fullmatch(host):
        return ""
    return host


def valid_session_id(value):
    return bool(SESSION_ID_RE.fullmatch((value or "").strip()))


def valid_phone(value):
    value = (value or "").strip()
    return not value or bool(PHONE_RE.fullmatch(value))


def _hash_key(action, ip, identifier):
    payload = f"{action}|{ip}|{(identifier or '').strip().lower()}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def consume_rate_limit(*, action, request, limit, window_seconds, identifier=""):
    now = timezone.now()
    key = _hash_key(action, client_ip(request), identifier)
    window = timedelta(seconds=window_seconds)

    for _ in range(2):
        try:
            with transaction.atomic():
                row = (
                    LimitationSecurite.objects
                    .select_for_update()
                    .filter(action=action, cle_hachee=key)
                    .first()
                )

                if row is None:
                    LimitationSecurite.objects.create(
                        action=action,
                        cle_hachee=key,
                        debut_fenetre=now,
                        compteur=1,
                    )
                    return True, 0

                if now - row.debut_fenetre >= window:
                    row.debut_fenetre = now
                    row.compteur = 1
                    row.save(
                        update_fields=[
                            "debut_fenetre",
                            "compteur",
                            "derniere_tentative",
                        ]
                    )
                    return True, 0

                if row.compteur >= limit:
                    retry = max(
                        1,
                        int((row.debut_fenetre + window - now).total_seconds()),
                    )
                    row.save(update_fields=["derniere_tentative"])
                    return False, retry

                row.compteur += 1
                row.save(update_fields=["compteur", "derniere_tentative"])
                return True, 0
        except IntegrityError:
            continue

    return False, window_seconds
