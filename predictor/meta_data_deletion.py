import base64
import hashlib
import hmac
import json
import secrets

from django.conf import settings
from django.http import JsonResponse
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .models import CompteConnecteExterne, CampagneExterne


def _decoder_base64url(value):
    value = str(value or "")
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _extraire_utilisateur_meta(signed_request):
    try:
        signature_part, payload_part = signed_request.split(".", 1)
    except ValueError as exc:
        raise ValueError("signed_request Meta invalide.") from exc

    fournisseur = settings.PREDICTNEED_EXTERNAL_CONNECTORS["meta_ads"]
    app_secret = str(fournisseur.get("client_secret") or "").strip()

    if not app_secret:
        raise ValueError("Secret Meta non configuré.")

    signature = _decoder_base64url(signature_part)

    signature_attendue = hmac.new(
        app_secret.encode("utf-8"),
        payload_part.encode("utf-8"),
        hashlib.sha256,
    ).digest()

    if not hmac.compare_digest(signature, signature_attendue):
        raise ValueError("Signature Meta invalide.")

    try:
        payload = json.loads(
            _decoder_base64url(payload_part).decode("utf-8")
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Payload Meta invalide.") from exc

    if str(payload.get("algorithm") or "").upper() != "HMAC-SHA256":
        raise ValueError("Algorithme Meta non autorisé.")

    user_id = str(payload.get("user_id") or "").strip()

    if not user_id.isdigit():
        raise ValueError("Identifiant utilisateur Meta invalide.")

    return user_id


@csrf_exempt
@require_http_methods(["GET", "POST"])
def meta_suppression_donnees_callback(request):
    if request.method == "GET":
        return JsonResponse({
            "status": "ok",
            "service": "PredictNeed IA Meta data deletion callback",
        })

    signed_request = request.POST.get("signed_request")

    if not signed_request:
        return JsonResponse(
            {"error": "signed_request manquant"},
            status=400,
        )

    try:
        user_id = _extraire_utilisateur_meta(signed_request)
    except ValueError as exc:
        return JsonResponse(
            {"error": str(exc)},
            status=400,
        )

    comptes = CompteConnecteExterne.objects.filter(
        plateforme="meta_ads",
        configuration__oauth_user_id=user_id,
    )

    CampagneExterne.objects.filter(
        compte__in=comptes
    ).delete()

    comptes.delete()

    confirmation_code = secrets.token_hex(16)

    status_url = request.build_absolute_uri(
        reverse("suppression_donnees")
    )

    status_url += f"?confirmation={confirmation_code}"

    return JsonResponse({
        "url": status_url,
        "confirmation_code": confirmation_code,
    })
