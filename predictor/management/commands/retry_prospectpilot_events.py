from django.core.management.base import BaseCommand

from predictor.services.prospectpilot_events import retry_due_events


class Command(BaseCommand):
    help = (
        "Envoie/relance les événements ProspectPilot en file (pending, failed "
        "échus, sending orphelins). Seul endroit du dépôt qui appelle réellement "
        "l'API ProspectPilot — même mécanisme cron que envoyer_relances_automatiques "
        "(pas de Celery dans ce dépôt)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit", type=int, default=100,
            help="Nombre maximum d'événements traités en un passage (défaut : 100).",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="N'envoie rien : affiche uniquement ce qui serait traité.",
        )

    def handle(self, *args, **options):
        resultat = retry_due_events(limit=options["limit"], dry_run=options["dry_run"])

        if resultat.get("dry_run"):
            self.stdout.write(
                self.style.SUCCESS(
                    f"[dry-run] À traiter : {resultat['would_process']} "
                    f"(ids : {resultat['event_ids']})"
                )
            )
            return

        self.stdout.write(
            self.style.SUCCESS(
                f"Réclamés : {resultat['claimed']} | Tentés : {resultat['attempted']} | "
                f"Envoyés : {resultat['sent']} | En attente de configuration : {resultat['pending_config']} | "
                f"Toujours en échec : {resultat['still_failed']} | Abandonnés : {resultat['dead_letter']}"
            )
        )
