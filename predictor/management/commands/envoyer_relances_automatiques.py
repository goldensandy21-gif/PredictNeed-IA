from django.core.management.base import BaseCommand

from predictor.automations import envoyer_relances_dues


class Command(BaseCommand):
    help = "Envoie les relances email dues pour les leads non traités."

    def handle(self, *args, **options):
        resultat = envoyer_relances_dues()

        self.stdout.write(
            self.style.SUCCESS(
                f"Relances envoyées : {resultat['envoyes']} | ignorées : {resultat['ignores']}"
            )
        )
