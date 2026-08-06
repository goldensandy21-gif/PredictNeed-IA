
import uuid
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.core.validators import validate_email
from django.utils import timezone
from .models import NewsletterInscription


def inscrire(*, prenom, email, consentement, source=""):
    email = (email or "").strip().lower()
    if not consentement:
        raise ValidationError("Vous devez accepter de recevoir les guides par email.")
    validate_email(email)
    item, _ = NewsletterInscription.objects.get_or_create(email=email)
    if item.statut == "confirmee":
        return item, False
    item.prenom = (prenom or "").strip()[:100]
    item.consentement = True
    item.version_confidentialite = settings.PREDICTNEED_PRIVACY_VERSION
    item.source = source[:255]
    item.date_consentement = timezone.now()
    item.date_desinscription = None
    item.statut = "en_attente"
    item.token = uuid.uuid4()
    item.save()
    base = (settings.PREDICTNEED_SITE_URL or "https://predictneed-ia.com").rstrip("/")
    send_mail(
        "Confirmez votre inscription aux guides PredictNeed IA",
        f"Bonjour,\n\nConfirmez votre inscription :\n{base}/newsletter/confirmer/{item.token}/\n\nPour annuler :\n{base}/newsletter/desinscription/{item.token}/\n\nPredictNeed IA",
        settings.DEFAULT_FROM_EMAIL,
        [email],
        fail_silently=False,
    )
    return item, True


def confirmer(token):
    item = NewsletterInscription.objects.filter(token=token).first()
    if item:
        item.statut = "confirmee"
        item.date_confirmation = timezone.now()
        item.date_desinscription = None
        item.save(update_fields=["statut", "date_confirmation", "date_desinscription", "date_mise_a_jour"])
    return item


def desinscrire(token):
    item = NewsletterInscription.objects.filter(token=token).first()
    if item:
        item.statut = "desinscrite"
        item.date_desinscription = timezone.now()
        item.save(update_fields=["statut", "date_desinscription", "date_mise_a_jour"])
    return item
