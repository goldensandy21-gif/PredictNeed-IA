"""Émission d'événements commerciaux vers ProspectPilot.

Seule voie normale d'écriture : `send_prospectpilot_event()`. Ne duplique
jamais la logique HMAC ailleurs.

Aucun appel réseau dans le chemin de requête utilisateur. `send_prospectpilot_
event()` se contente d'un enregistrement idempotent (ProspectPilotOutboundEvent,
status="pending") et retourne immédiatement — le middleware d'arrivée, le
simulateur, l'inscription, le checkout et le webhook Stripe ne font donc
jamais d'E/S réseau vers ProspectPilot.

L'envoi réel n'a lieu que hors requête, via `retry_due_events()` — appelée par
la commande de gestion `retry_prospectpilot_events` (même mécanisme cron que
`envoyer_relances_automatiques` ; ce dépôt n'a pas de Celery). Aucune action
métier PredictNeed n'attend ni ne dépend de la réussite de cet envoi.
"""
import hashlib
import hmac
import json
import logging
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.db import IntegrityError, transaction
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


def _check_configuration():
    """Une absence de configuration locale n'est PAS une erreur serveur : elle
    ne doit jamais mener à un dead_letter (voir `_attempt_delivery`)."""
    if not settings.PROSPECTPILOT_EVENTS_ENABLED:
        return False, "PROSPECTPILOT_EVENTS_ENABLED=False"
    if not settings.PROSPECTPILOT_API_URL:
        return False, "PROSPECTPILOT_API_URL non configuré."
    if not settings.PROSPECTPILOT_SHARED_SECRET:
        return False, "PROSPECTPILOT_SHARED_SECRET non configuré."
    return True, ""


def _post_to_prospectpilot(payload_dict):
    """Un seul essai réseau, en supposant la configuration déjà vérifiée
    présente par l'appelant. Ne lève jamais : retourne (ok, status_code, error, retryable)."""
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
        # 400 = payload invalide, jamais retryable.
        # 401/403 = signature/secret rejetés par un serveur RÉELLEMENT configuré
        # (différent d'une absence locale de configuration) : jamais retryable.
        # 429/5xx = transitoire, retryable avec backoff.
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
    """Enqueue rapide et fiable — AUCUN appel réseau ici. Retourne l'objet
    ProspectPilotOutboundEvent (déjà existant si l'idempotency_key est un doublon).
    L'envoi effectif est fait plus tard par `retry_due_events()`."""
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


def _finalize_configuration_missing(event, config_error):
    event.status = "pending_config"
    event.last_error = config_error
    event.next_retry_at = None
    event.save(update_fields=["status", "last_error", "next_retry_at"])
    return "pending_config"


def _attempt_delivery(event):
    """Appelée UNIQUEMENT par `retry_due_events()`, jamais depuis une requête
    utilisateur. `event` doit déjà être marqué status="sending" (réclamé)."""
    config_ok, config_error = _check_configuration()
    if not config_ok:
        # Ne compte pas comme une tentative réelle : aucun appel réseau n'a eu
        # lieu, donc pas d'incrément d'attempt_count et jamais de dead_letter.
        return _finalize_configuration_missing(event, config_error)

    event.attempt_count += 1
    event.save(update_fields=["attempt_count"])

    ok, status_code, error, retryable = _post_to_prospectpilot(event.payload)

    if ok:
        event.status = "sent"
        event.sent_at = timezone.now()
        event.last_error = ""
        event.next_retry_at = None
        event.save(update_fields=["status", "sent_at", "last_error", "next_retry_at"])
        return "sent"

    event.last_error = (error or "")[:500]
    if retryable and event.attempt_count < MAX_ATTEMPTS:
        backoff_seconds = min(3600, 30 * (2 ** (event.attempt_count - 1)))
        event.status = "failed"
        event.next_retry_at = timezone.now() + timezone.timedelta(seconds=backoff_seconds)
    else:
        # Payload définitivement invalide (400), authentification réellement
        # rejetée par un serveur configuré (401/403), ou nombre max de
        # tentatives atteint pour une erreur transitoire (429/5xx/réseau).
        event.status = "dead_letter"
        event.next_retry_at = None
    event.save(update_fields=["status", "last_error", "next_retry_at"])
    return event.status


def _eligible_filter(now, stale_cutoff):
    return (
        Q(status="pending")
        | Q(status="pending_config")
        | Q(status="failed", next_retry_at__lte=now)
        | Q(status="failed", next_retry_at__isnull=True)
        | Q(status="sending", last_attempt_at__lt=stale_cutoff)  # orphelin après un crash
    )


def retry_due_events(limit=100, dry_run=False):
    """Traite pending + failed échus + sending orphelins (crash après claim).
    Ignore sent/dead_letter et les événements non encore dus.

    Sûre en cas d'exécutions concurrentes : la réclamation ("claim") se fait
    par une UPDATE conditionnelle qui revérifie les mêmes critères
    d'éligibilité dans son WHERE — si un autre runner a déjà réclamé une ligne
    entre la lecture et l'écriture, la condition ne matche plus pour cette
    ligne côté second runner et elle n'est pas retraitée deux fois. Cette
    approche fonctionne aussi bien sur SQLite (dev/tests) que sur PostgreSQL
    (production), contrairement à select_for_update(), non supporté par
    SQLite. L'idempotency key côté ProspectPilot reste la défense finale
    contre un double traitement résiduel.
    """
    now = timezone.now()
    stale_cutoff = now - timezone.timedelta(seconds=settings.PROSPECTPILOT_STALE_SENDING_SECONDS)
    base_filter = _eligible_filter(now, stale_cutoff)

    candidate_ids = list(
        ProspectPilotOutboundEvent.objects.filter(base_filter)
        .order_by("created_at")
        .values_list("pk", flat=True)[:limit]
    )

    if dry_run:
        return {"dry_run": True, "would_process": len(candidate_ids), "event_ids": candidate_ids}

    results = {
        "dry_run": False, "claimed": 0, "attempted": 0, "sent": 0,
        "still_failed": 0, "dead_letter": 0, "pending_config": 0,
    }
    if not candidate_ids:
        return results

    with transaction.atomic():
        ProspectPilotOutboundEvent.objects.filter(base_filter, pk__in=candidate_ids).update(
            status="sending", last_attempt_at=now,
        )
        claimed_id_set = set(
            ProspectPilotOutboundEvent.objects.filter(
                pk__in=candidate_ids, status="sending", last_attempt_at=now,
            ).values_list("pk", flat=True)
        )
    # Préserve l'ordre chronologique de `candidate_ids` (issu du .order_by("created_at")
    # ci-dessus) : la requête de re-vérification ci-dessus n'a pas d'ordre garanti, et
    # traiter les événements dans le désordre peut inverser des transitions d'état côté
    # ProspectPilot (ex. signup_completed traité après subscription_activated).
    claimed_ids = [pk for pk in candidate_ids if pk in claimed_id_set]
    results["claimed"] = len(claimed_ids)

    for event_id in claimed_ids:
        event = ProspectPilotOutboundEvent.objects.get(pk=event_id)
        outcome = _attempt_delivery(event)
        results["attempted"] += 1
        if outcome == "sent":
            results["sent"] += 1
        elif outcome == "dead_letter":
            results["dead_letter"] += 1
        elif outcome == "pending_config":
            results["pending_config"] += 1
        else:
            results["still_failed"] += 1
    return results
