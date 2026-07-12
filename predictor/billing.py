import base64
import hashlib
import hmac
import json
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings


STRIPE_API_BASE = "https://api.stripe.com/v1"


class StripeConfigurationError(Exception):
    pass


class StripeAPIError(Exception):
    pass


def format_subscription_price():
    amount = settings.PREDICTNEED_SUBSCRIPTION_PRICE_CENTS / 100
    return f"{amount:,.0f} €".replace(",", " ")


def stripe_is_configured():
    return bool(settings.STRIPE_SECRET_KEY)


def _stripe_request(method, endpoint, payload=None):
    if not settings.STRIPE_SECRET_KEY:
        raise StripeConfigurationError("La clé secrète Stripe n'est pas configurée.")

    url = f"{STRIPE_API_BASE}{endpoint}"
    encoded_payload = None

    if payload is not None:
        encoded_payload = urlencode(payload).encode("utf-8")

    token = base64.b64encode(f"{settings.STRIPE_SECRET_KEY}:".encode("utf-8")).decode("ascii")
    request = Request(
        url,
        data=encoded_payload,
        method=method,
        headers={
            "Authorization": f"Basic {token}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )

    try:
        with urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        try:
            body = json.loads(exc.read().decode("utf-8"))
            message = body.get("error", {}).get("message", "Erreur Stripe.")
        except (json.JSONDecodeError, UnicodeDecodeError):
            message = "Erreur Stripe."
        raise StripeAPIError(message) from exc
    except URLError as exc:
        raise StripeAPIError("Le service de paiement est momentanément indisponible.") from exc


def create_subscription_checkout_session(*, client, success_url, cancel_url):
    payload = {
        "mode": "subscription",
        "success_url": success_url,
        "cancel_url": cancel_url,
        "customer_email": client.utilisateur.email,
        "client_reference_id": str(client.id),
        "billing_address_collection": "required",
        "tax_id_collection[enabled]": "true",
        "metadata[client_id]": str(client.id),
        "metadata[user_id]": str(client.utilisateur_id),
        "subscription_data[metadata][client_id]": str(client.id),
        "subscription_data[metadata][user_id]": str(client.utilisateur_id),
        "line_items[0][quantity]": "1",
    }

    if settings.STRIPE_AUTOMATIC_TAX:
        payload["automatic_tax[enabled]"] = "true"

    if settings.STRIPE_PRICE_ID:
        payload["line_items[0][price]"] = settings.STRIPE_PRICE_ID
    else:
        payload.update(
            {
                "line_items[0][price_data][currency]": settings.PREDICTNEED_SUBSCRIPTION_CURRENCY,
                "line_items[0][price_data][product_data][name]": settings.PREDICTNEED_SUBSCRIPTION_NAME,
                "line_items[0][price_data][unit_amount]": str(
                    settings.PREDICTNEED_SUBSCRIPTION_PRICE_CENTS
                ),
                "line_items[0][price_data][recurring][interval]": settings.PREDICTNEED_SUBSCRIPTION_INTERVAL,
            }
        )

    return _stripe_request("POST", "/checkout/sessions", payload)


def retrieve_checkout_session(session_id):
    return _stripe_request("GET", f"/checkout/sessions/{session_id}")


def verify_stripe_signature(payload, signature_header, webhook_secret, tolerance=300):
    if not webhook_secret:
        raise StripeConfigurationError("Le secret webhook Stripe n'est pas configuré.")

    parts = {}
    for item in signature_header.split(","):
        if "=" in item:
            key, value = item.split("=", 1)
            parts.setdefault(key, []).append(value)

    timestamps = parts.get("t", [])
    signatures = parts.get("v1", [])

    if not timestamps or not signatures:
        return False

    try:
        timestamp = int(timestamps[0])
    except ValueError:
        return False

    if abs(time.time() - timestamp) > tolerance:
        return False

    signed_payload = f"{timestamp}.".encode("utf-8") + payload
    expected = hmac.new(
        webhook_secret.encode("utf-8"),
        signed_payload,
        hashlib.sha256,
    ).hexdigest()

    return any(hmac.compare_digest(expected, signature) for signature in signatures)
