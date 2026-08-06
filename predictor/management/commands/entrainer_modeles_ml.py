
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from predictor.ml_training import entrainer_site
from predictor.models import JournalMaintenance, SiteClient


class Command(BaseCommand):
    help = (
        "Entraîne un modèle supervisé séparé pour chaque site disposant "
        "d'assez de résultats convertis et perdus."
    )

    def add_arguments(self, parser):
        parser.add_argument("--site-id", type=int)
        parser.add_argument(
            "--minimum-samples",
            type=int,
            default=settings.PREDICTNEED_ML_MIN_SAMPLES,
        )
        parser.add_argument(
            "--minimum-per-class",
            type=int,
            default=settings.PREDICTNEED_ML_MIN_PER_CLASS,
        )
        parser.add_argument(
            "--minimum-balanced-accuracy",
            type=float,
            default=settings.PREDICTNEED_ML_MIN_BALANCED_ACCURACY,
        )
        parser.add_argument(
            "--activate-low-quality",
            action="store_true",
            help=(
                "Active un modèle même si le seuil de qualité n'est pas atteint. "
                "Cette option ne doit pas être utilisée par l'ordonnanceur."
            ),
        )

    def handle(self, *args, **options):
        journal = JournalMaintenance.objects.create(
            type_operation="entrainement_ml",
            statut="en_cours",
        )
        details = {"sites": []}

        try:
            sites = SiteClient.objects.filter(
                actif=True,
                module_prediction_avancee_actif=True,
            ).order_by("pk")
            if options["site_id"]:
                sites = sites.filter(pk=options["site_id"])

            if not sites.exists():
                self.stdout.write(
                    self.style.WARNING(
                        "Aucun site actif avec le module de prédiction avancée."
                    )
                )

            for site in sites:
                result = entrainer_site(
                    site,
                    minimum_samples=options["minimum_samples"],
                    minimum_per_class=options["minimum_per_class"],
                    minimum_balanced_accuracy=options[
                        "minimum_balanced_accuracy"
                    ],
                    activate_low_quality=options["activate_low_quality"],
                )
                details["sites"].append(
                    {
                        "site_id": site.pk,
                        "site": site.nom_site,
                        "status": result.status,
                        "message": result.message,
                        "model_id": result.model_id,
                        "active": result.active,
                        "samples": result.samples,
                        "positives": result.positives,
                        "negatives": result.negatives,
                        "metrics": result.metrics or {},
                    }
                )

                style = (
                    self.style.SUCCESS
                    if result.active
                    else self.style.WARNING
                )
                self.stdout.write(style(f"{site.nom_site} : {result.message}"))

            journal.statut = "succes"
            journal.details = details
            journal.date_fin = timezone.now()
            journal.save(
                update_fields=["statut", "details", "date_fin"]
            )
        except Exception as exc:
            journal.statut = "erreur"
            journal.details = details
            journal.message_erreur = str(exc)[:4000]
            journal.date_fin = timezone.now()
            journal.save(
                update_fields=[
                    "statut",
                    "details",
                    "message_erreur",
                    "date_fin",
                ]
            )
            raise CommandError(str(exc)) from exc
