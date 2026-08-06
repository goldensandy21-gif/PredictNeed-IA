
from django.conf import settings
from django.core import signing
from django.core.mail import send_mail
from django.urls import reverse
from django.utils import timezone

from .models import ClientProfessionnel


EMAIL_VERIFICATION_SALT = "predictneed-email-verification-v1"


def build_verification_token(client):
    return signing.dumps(
        {
            "client_id": client.pk,
            "email": (client.utilisateur.email or "").strip().lower(),
        },
        salt=EMAIL_VERIFICATION_SALT,
        compress=True,
    )


def send_verification_email(client):
    email = (client.utilisateur.email or "").strip().lower()
    if not email:
        return False

    base = (settings.PREDICTNEED_SITE_URL or "https://predictneed-ia.com").rstrip("/")
    token = build_verification_token(client)
    path = reverse("confirmer_email_compte", args=[token])
    confirmation_url = f"{base}{path}"

    send_mail(
        "Confirmez votre adresse email PredictNeed IA",
        (
            "Bonjour,\n\n"
            "Votre compte PredictNeed IA a bien été créé. "
            "Confirmez votre adresse email en ouvrant ce lien :\n"
            f"{confirmation_url}\n\n"
            "Votre essai reste accessible pendant la vérification.\n\n"
            "PredictNeed IA"
        ),
        settings.DEFAULT_FROM_EMAIL,
        [email],
        fail_silently=False,
    )
    return True


def confirm_email(token, max_age=7 * 24 * 60 * 60):
    try:
        payload = signing.loads(
            token,
            salt=EMAIL_VERIFICATION_SALT,
            max_age=max_age,
        )
    except signing.BadSignature:
        return None

    client = (
        ClientProfessionnel.objects
        .select_related("utilisateur")
        .filter(pk=payload.get("client_id"))
        .first()
    )
    if client is None:
        return None

    current_email = (client.utilisateur.email or "").strip().lower()
    if not current_email or current_email != payload.get("email"):
        return None

    if client.email_verifie_le is None:
        client.email_verifie_le = timezone.now()
        client.save(update_fields=["email_verifie_le"])
    return client
