from django.core.management.base import BaseCommand

from predictor.services.prospectpilot_events import retry_due_events


class Command(BaseCommand):
    help = "Relance les événements ProspectPilot en échec transitoire (même mécanisme cron que envoyer_relances_automatiques — pas de Celery dans ce dépôt)."

    def handle(self, *args, **options):
        resultat = retry_due_events()
        self.stdout.write(
            self.style.SUCCESS(
                f"Tentés : {resultat['attempted']} | Envoyés : {resultat['sent']} | "
                f"Toujours en échec : {resultat['still_failed']} | Abandonnés : {resultat['dead_letter']}"
            )
        )
