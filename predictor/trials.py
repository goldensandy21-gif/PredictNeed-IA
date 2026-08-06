
from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from .models import ClientProfessionnel


REMINDER_FIELDS = {
    15: "rappel_15_jours_envoye_le",
    7: "rappel_7_jours_envoye_le",
    2: "rappel_2_jours_envoye_le",
}


def _activation_url():
    base_url = (
        settings.PREDICTNEED_SITE_URL
        or "https://predictneed-ia.com"
    ).rstrip("/")
    return f"{base_url}/dashboard/"


def _send_trial_email(client, subject, body):
    email = (client.utilisateur.email or "").strip()
    if not email:
        return False

    send_mail(
        subject,
        body,
        settings.DEFAULT_FROM_EMAIL,
        [email],
        fail_silently=False,
    )
    return True


def _days_remaining(client, now):
    end_date = timezone.localtime(client.date_fin_essai).date()
    today = timezone.localtime(now).date()
    return (end_date - today).days


def traiter_essais_gratuits(now=None):
    now = now or timezone.now()
    results = {
        "rappels_envoyes": 0,
        "expirations": 0,
        "erreurs": 0,
    }

    client_ids = list(
        ClientProfessionnel.objects.filter(
            statut_abonnement="essai"
        ).values_list("id", flat=True)
    )

    for client_id in client_ids:
        try:
            with transaction.atomic():
                client = (
                    ClientProfessionnel.objects
                    .select_for_update()
                    .select_related("utilisateur")
                    .get(pk=client_id)
                )

                if not client.date_debut_essai or not client.date_fin_essai:
                    client.initialiser_essai(maintenant=now)

                days_remaining = _days_remaining(client, now)

                if now >= client.date_fin_essai:
                    client.statut_abonnement = "expire"
                    client.save(update_fields=["statut_abonnement"])
                    client.utilisateur.is_active = True
                    client.utilisateur.save(
                        update_fields=["is_active"]
                    )
                    client.sites.update(actif=True)
                    results["expirations"] += 1

                    if not client.email_expiration_envoye_le:
                        sent = _send_trial_email(
                            client,
                            "Votre essai PredictNeed IA est terminé",
                            (
                                "Bonjour,\n\n"
                                "Votre période d'essai gratuite de "
                                f"{settings.PREDICTNEED_SUBSCRIPTION_TRIAL_DAYS} "
                                "jours est terminée.\n\n"
                                "Votre compte et vos données sont conservés. "
                                "Vous pouvez toujours vous connecter, mais les "
                                "prédictions, statistiques, leads et autres "
                                "données sont temporairement verrouillés.\n\n"
                                "Pour réactiver votre accès :\n"
                                f"{_activation_url()}\n\n"
                                "L'équipe PredictNeed IA"
                            ),
                        )
                        if sent:
                            client.email_expiration_envoye_le = now
                            client.save(
                                update_fields=[
                                    "email_expiration_envoye_le"
                                ]
                            )
                    continue

                reminder_field = REMINDER_FIELDS.get(days_remaining)
                if not reminder_field or getattr(client, reminder_field):
                    continue

                sent = _send_trial_email(
                    client,
                    (
                        "Votre essai PredictNeed IA se termine "
                        f"dans {days_remaining} jours"
                    ),
                    (
                        "Bonjour,\n\n"
                        "Votre essai gratuit PredictNeed IA se termine "
                        f"dans {days_remaining} jours, le "
                        f"{timezone.localtime(client.date_fin_essai):%d/%m/%Y}.\n\n"
                        "Aucune carte bancaire n'a été demandée au début "
                        "de l'essai. Votre compte et vos données resteront "
                        "conservés après l'expiration.\n\n"
                        "Pour poursuivre avec l'abonnement :\n"
                        f"{_activation_url()}\n\n"
                        "L'équipe PredictNeed IA"
                    ),
                )

                if sent:
                    setattr(client, reminder_field, now)
                    client.save(update_fields=[reminder_field])
                    results["rappels_envoyes"] += 1

        except Exception:
            results["erreurs"] += 1

    return results
