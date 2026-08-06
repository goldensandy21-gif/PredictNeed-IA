
from django.core.management.base import BaseCommand

from predictor.trials import traiter_essais_gratuits


class Command(BaseCommand):
    help = (
        "Envoie les rappels J-15, J-7 et J-2, puis expire "
        "les essais gratuits arrivés à leur terme."
    )

    def handle(self, *args, **options):
        results = traiter_essais_gratuits()
        self.stdout.write(
            self.style.SUCCESS(
                "Rappels envoyés : "
                f"{results['rappels_envoyes']} | "
                "Essais expirés : "
                f"{results['expirations']} | "
                "Erreurs : "
                f"{results['erreurs']}"
            )
        )
