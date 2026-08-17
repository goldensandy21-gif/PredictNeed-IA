"""Émission d'événements commerciaux vers ProspectPilot.

Seule voie normale d'envoi : `send_prospectpilot_event()`. Ne duplique jamais
la logique HMAC ailleurs.

Fiabilité sans Celery (ce dépôt n'utilise pas de file de tâches) : l'événement
est d'abord journalisé en base (ProspectPilotOutboundEvent, contrainte
d'unicité sur `event_id`) puis un essai réseau synchrone rapide est tenté. En
cas d'échec transitoire, `retry_due_events()` — appelée par la commande de
gestion `retry_prospectpilot_events`, au même titre que
`envoyer_relances_automatiques` — retente plus tard. Aucune action métier
PredictNeed (paiement, inscription) n'attend ni ne dépend de la réussite de
cet envoi.
"""
import hashlib
import hmac
import json
import logging
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.db import IntegrityError
from django.db.models import Q
from django.utils import timezone

from ..models import ProspectPilotOutboundEvent

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 6
EVENTS_PATH = "/api/predictneed/events/"

# Ne jamais transmettre : numéro de carte, CVC, token de carte, mot de passe,
# secret Stripe, session/cookie d'authentification, contenu personnel inutile.
_FORBIDDEN_PAYLOAD_KEYS = {
    "card_number", "cvc", "card", "payment_method", "password",
    "stripe_secret_key", "session_auth", "cookie",
}


def normalize_to_monthly(amount, interval):
    """1188 EUR/an -> 99 EUR de MRR ; 99 EUR/mois -> 99 EUR de MRR."""
    if amount is None:
        return None
    divisor = {"day": 1 / 30, "week": 1 / 4.345, "month": 1, "year": 12}.get(interval, 1)
    return round(amount / divisor, 2)


def _sign(secret, timestamp, body):
    message = f"{timestamp}.{body}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def _post_to_prospectpilot(payload_dict):
    """Un seul essai réseau. Ne lève jamais : retourne (ok, status_code, error, retryable)."""
    if not settings.PROSPECTPILOT_EVENTS_ENABLED:
        return False, None, "PROSPECTPILOT_EVENTS_ENABLED=False", False
    if not settings.PROSPECTPILOT_API_URL or not settings.PROSPECTPILOT_SHARED_SECRET:
        return False, None, "PROSPECTPILOT_API_URL / PROSPECTPILOT_SHARED_SECRET non configurés.", False

    body = json.dumps(payload_dict, separators=(",", ":"), sort_keys=True, default=str)
    timestamp = int(time.time())
    signature = _sign(settings.PROSPECTPILOT_SHARED_SECRET, timestamp, body)
    url = settings.PROSPECTPILOT_API_URL.rstrip("/") + EVENTS_PATH

    request = Request(
        url,
        data=body.encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-PredictNeed-Signature": f"t={timestamp},v1={signature}",
        },
    )
    try:
        with urlopen(request, timeout=settings.PROSPECTPILOT_EVENT_TIMEOUT) as response:
            response.read()
            return True, response.status, "", False
    except HTTPError as exc:
        # 400/401/403 = payload ou signature invalide : jamais transitoire, pas de retry.
        retryable = exc.code == 429 or exc.code >= 500
        return False, exc.code, f"HTTP {exc.code}", retryable
    except URLError as exc:
        return False, None, f"Erreur réseau : {exc.reason}", True
    except TimeoutError:
        return False, None, "Timeout", True
    except Exception as exc:  # défense en profondeur : ne jamais casser l'appelant
        logger.exception("Erreur inattendue lors de l'appel ProspectPilot.")
        return False, None, str(exc)[:200], True


def _sanitize_metadata(metadata):
    if not isinstance(metadata, dict):
        return {}
    return {k: v for k, v in metadata.items() if k not in _FORBIDDEN_PAYLOAD_KEYS}


def send_prospectpilot_event(event_type, attribution=None, idempotency_key=None, occurred_at=None, **extra_fields):
    """Journalise puis tente d'envoyer un événement. Retourne l'objet
    ProspectPilotOutboundEvent (déjà existant si l'idempotency_key est un doublon)."""
    for forbidden in _FORBIDDEN_PAYLOAD_KEYS:
        extra_fields.pop(forbidden, None)

    idempotency_key = idempotency_key or f"{(attribution.token if attribution else 'no-attribution')}:{event_type}:{int(time.time())}"
    occurred_at = occurred_at or timezone.now()
    metadata = _sanitize_metadata(extra_fields.pop("metadata", {}))

    payload = {
        "event_type": event_type,
        "ppt": attribution.token if attribution else "",
        "idempotency_key": idempotency_key,
        "occurred_at": occurred_at.isoformat(),
        "metadata": metadata,
    }
    for key, value in extra_fields.items():
        if value is not None:
            payload[key] = value

    try:
        event, created = ProspectPilotOutboundEvent.objects.get_or_create(
            event_id=idempotency_key,
            defaults={"event_type": event_type, "attribution": attribution, "payload": payload, "status": "pending"},
        )
    except IntegrityError:
        # Course concurrente sur la même idempotency_key : l'autre requête a gagné, on la relit.
        event = ProspectPilotOutboundEvent.objects.get(event_id=idempotency_key)
        created = False

    if not created:
        logger.info("Événement ProspectPilot déjà journalisé (idempotency_key=%s), pas de renvoi.", idempotency_key)
        return event

    _attempt_delivery(event)
    return event


def _attempt_delivery(event):
    event.status = "sending"
    event.attempt_count += 1
    event.last_attempt_at = timezone.now()
    event.save(update_fields=["status", "attempt_count", "last_attempt_at"])

    ok, status_code, error, retryable = _post_to_prospectpilot(event.payload)

    if ok:
        event.status = "sent"
        event.sent_at = timezone.now()
        event.last_error = ""
        event.next_retry_at = None
        event.save(update_fields=["status", "sent_at", "last_error", "next_retry_at"])
        return True

    event.last_error = (error or "")[:500]
    if retryable and event.attempt_count < MAX_ATTEMPTS:
        backoff_seconds = min(3600, 30 * (2 ** (event.attempt_count - 1)))
        event.status = "failed"
        event.next_retry_at = timezone.now() + timezone.timedelta(seconds=backoff_seconds)
    else:
        # Erreur non transitoire (400/401/403) ou nombre max de tentatives atteint.
        event.status = "dead_letter"
        event.next_retry_at = None
    event.save(update_fields=["status", "last_error", "next_retry_at"])
    return False


def retry_due_events(limit=100):
    """Appelée par la commande `retry_prospectpilot_events` (cron externe,
    même mécanisme que `envoyer_relances_automatiques` — pas de Celery ici)."""
    now = timezone.now()
    due = ProspectPilotOutboundEvent.objects.filter(status="failed").filter(
        Q(next_retry_at__lte=now) | Q(next_retry_at__isnull=True)
    )[:limit]

    results = {"attempted": 0, "sent": 0, "still_failed": 0, "dead_letter": 0}
    for event in due:
        results["attempted"] += 1
        ok = _attempt_delivery(event)
        if ok:
            results["sent"] += 1
        elif event.status == "dead_letter":
            results["dead_letter"] += 1
        else:
            results["still_failed"] += 1
    return results
