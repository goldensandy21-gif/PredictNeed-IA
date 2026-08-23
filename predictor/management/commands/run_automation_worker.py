import time
import logging
from django.core.management.base import BaseCommand
from django.utils import timezone
from predictor.automations import envoyer_relances_dues
from predictor.services.prospectpilot_events import retry_due_events

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Worker pour traiter les automatisations email et les événements ProspectPilot"

    def add_arguments(self, parser):
        parser.add_argument(
            '--interval',
            type=int,
            default=60,
            help='Intervalle en secondes entre chaque cycle de traitement'
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=100,
            help="Nombre maximum d'événements à traiter par cycle"
        )
        parser.add_argument(
            '--once',
            action='store_true',
            help="Exécuter une seule fois et quitter"
        )

    def handle(self, *args, **options):
        interval = options['interval']
        limit = options['limit']
        once = options['once']

        self.stdout.write(
            self.style.SUCCESS(
                f"Worker démarré - Intervalle: {interval}s, Limite: {limit}, "
                f"Mode: {'une fois' if once else 'continu'}"
            )
        )

        if once:
            self._run_cycle(limit)
            return

        while True:
            try:
                self._run_cycle(limit)
                self.stdout.write(f"Cycle terminé. Prochain cycle dans {interval} secondes...")
                time.sleep(interval)
            except KeyboardInterrupt:
                self.stdout.write(self.style.WARNING("Arrêt du worker demandé"))
                break
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Erreur dans le cycle: {e}"))
                logger.exception("Erreur dans le worker automation")
                time.sleep(interval)

    def _run_cycle(self, limit):
        """Exécute un cycle complet de traitement"""
        now = timezone.now()

        # Traitement des relances email
        try:
            resultat_relances = envoyer_relances_dues(now=now)
            self.stdout.write(
                self.style.SUCCESS(
                    f"Relances email: {resultat_relances['envoyes']} envoyées, "
                    f"{resultat_relances['ignores']} ignorées"
                )
            )
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Erreur relances email: {e}"))
            logger.exception("Erreur relances email")

        # Traitement des événements ProspectPilot
        try:
            resultat_events = retry_due_events(limit=limit)
            self.stdout.write(
                self.style.SUCCESS(
                    f"Événements PP: {resultat_events['claimed']} réclamés, "
                    f"{resultat_events['sent']} envoyés"
                )
            )
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Erreur événements PP: {e}"))
            logger.exception("Erreur événements ProspectPilot")