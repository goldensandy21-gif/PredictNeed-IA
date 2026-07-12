from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from predictor.models import (
    EvenementUtilisateur,
    LeadCapture,
    PredictionBesoin,
    SessionVisiteur,
)


class Command(BaseCommand):
    help = "Purge les données PredictNeed IA au-delà des durées de conservation RGPD configurées."

    def add_arguments(self, parser):
        parser.add_argument(
            "--analytics-days",
            type=int,
            default=395,
            help="Durée de conservation des sessions, événements et prédictions détaillées. 395 jours correspond à environ 13 mois.",
        )
        parser.add_argument(
            "--lead-days",
            type=int,
            default=1095,
            help="Durée de conservation des leads sans contact actif, par défaut 3 ans.",
        )
        parser.add_argument(
            "--execute",
            action="store_true",
            help="Exécute réellement la purge. Sans cette option, la commande affiche seulement les volumes concernés.",
        )

    def handle(self, *args, **options):
        analytics_cutoff = timezone.now() - timedelta(days=options["analytics_days"])
        lead_cutoff = timezone.now() - timedelta(days=options["lead_days"])
        execute = options["execute"]

        predictions = PredictionBesoin.objects.filter(date_creation__lt=analytics_cutoff)
        evenements = EvenementUtilisateur.objects.filter(date_creation__lt=analytics_cutoff)
        leads = LeadCapture.objects.filter(date_creation__lt=lead_cutoff)
        sessions_sans_lead = SessionVisiteur.objects.filter(
            derniere_activite__lt=analytics_cutoff,
            leads__isnull=True,
        ).distinct()

        counts = {
            "predictions": predictions.count(),
            "evenements": evenements.count(),
            "leads": leads.count(),
            "sessions_sans_lead": sessions_sans_lead.count(),
        }

        if not execute:
            self.stdout.write(self.style.WARNING("Simulation uniquement. Ajoutez --execute pour purger réellement."))
            self._print_counts(counts)
            return

        deleted = {}
        deleted["leads"] = leads.delete()[0]
        deleted["predictions"] = predictions.delete()[0]
        deleted["evenements"] = evenements.delete()[0]

        sessions_sans_lead = SessionVisiteur.objects.filter(
            derniere_activite__lt=analytics_cutoff,
            leads__isnull=True,
        ).distinct()
        deleted["sessions_sans_lead"] = sessions_sans_lead.delete()[0]

        self.stdout.write(self.style.SUCCESS("Purge RGPD terminée."))
        self._print_counts(deleted)

    def _print_counts(self, counts):
        self.stdout.write(f"Prédictions concernées : {counts['predictions']}")
        self.stdout.write(f"Événements concernés : {counts['evenements']}")
        self.stdout.write(f"Leads concernés : {counts['leads']}")
        self.stdout.write(f"Sessions sans lead concernées : {counts['sessions_sans_lead']}")
