
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from predictor.models import LimitationSecurite, NewsletterInscription


class Command(BaseCommand):
    help = "Supprime les anciennes fenêtres de limitation et les confirmations newsletter abandonnées."

    def handle(self, *args, **options):
        limite_securite = timezone.now() - timedelta(days=2)
        limite_newsletter = timezone.now() - timedelta(days=30)

        limitations, _ = LimitationSecurite.objects.filter(
            derniere_tentative__lt=limite_securite
        ).delete()
        newsletters, _ = NewsletterInscription.objects.filter(
            statut="en_attente",
            date_creation__lt=limite_newsletter,
        ).delete()

        self.stdout.write(
            self.style.SUCCESS(
                f"Limitations supprimées : {limitations} | "
                f"Inscriptions newsletter en attente supprimées : {newsletters}"
            )
        )
