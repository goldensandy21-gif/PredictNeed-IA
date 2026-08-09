from django.core.management.base import BaseCommand, CommandError
from django.db.models import F, Q

from predictor.models import (
    AutomatisationEmail,
    CampagneExterne,
    ClientProfessionnel,
    CompteConnecteExterne,
    LeadCapture,
    MesureCampagneExterne,
    ModeleMachineLearning,
    Vente,
)


def _devise_invalide(devise):
    devise = str(devise or "").strip()
    return len(devise) != 3 or not devise.isalpha() or devise.upper() != devise


class Command(BaseCommand):
    help = (
        "Audite en lecture seule les données legacy à vérifier avant une "
        "migration ou un déploiement production."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--fail-on-issues",
            action="store_true",
            help=(
                "Retourne une erreur si des points legacy à traiter sont "
                "détectés. Ne modifie aucune donnée."
            ),
        )

    def handle(self, *args, **options):
        checks = [
            (
                "connecteurs_sans_site",
                CompteConnecteExterne.objects.filter(site__isnull=True).count(),
                "à rattacher à un site avant toute synchronisation native",
            ),
            (
                "automatisations_sans_site",
                AutomatisationEmail.objects.filter(site__isnull=True).count(),
                "conservées pour audit, ignorées par le scheduler",
            ),
            (
                "campagnes_sans_site",
                CampagneExterne.objects.filter(site__isnull=True).count(),
                "à vérifier : le dashboard ne les expose que via le compte rattaché",
            ),
            (
                "campagnes_site_different_compte",
                CampagneExterne.objects.filter(
                    Q(compte__site__isnull=True)
                    | (
                        Q(site__isnull=False)
                        & ~Q(site_id=F("compte__site_id"))
                    )
                ).count(),
                "à corriger avant exploitation multi-site",
            ),
            (
                "mesures_site_different_compte",
                MesureCampagneExterne.objects.filter(
                    Q(compte__site__isnull=True)
                    | ~Q(site_id=F("compte__site_id"))
                ).count(),
                "à corriger avant calculs publicitaires",
            ),
            (
                "leads_session_sans_site",
                LeadCapture.objects.filter(session__site__isnull=True).count(),
                "à vérifier : les leads clients doivent venir d'une session de site",
            ),
            (
                "ventes_montant_non_positif",
                Vente.objects.filter(montant__lte=0).count(),
                "à corriger avant reporting financier",
            ),
            (
                "clients_essai_sans_dates",
                ClientProfessionnel.objects.filter(
                    statut_abonnement="essai",
                )
                .filter(
                    Q(date_debut_essai__isnull=True)
                    | Q(date_fin_essai__isnull=True)
                )
                .count(),
                "à initialiser avant activation scheduler",
            ),
            (
                "modeles_ml_actifs_sans_echantillons",
                ModeleMachineLearning.objects.filter(
                    actif=True,
                    nombre_echantillons=0,
                ).count(),
                "à désactiver ou réentraîner avant décision ML",
            ),
        ]

        devise_checks = [
            (
                "ventes_devise_invalide",
                Vente.objects.values_list("devise", flat=True),
                "à corriger avant calcul ROAS/ROI",
            ),
            (
                "campagnes_devise_invalide",
                CampagneExterne.objects.values_list("devise", flat=True),
                "à corriger avant agrégats publicitaires",
            ),
            (
                "mesures_devise_invalide",
                MesureCampagneExterne.objects.values_list("devise", flat=True),
                "à corriger avant agrégats publicitaires",
            ),
        ]

        for name, values, message in devise_checks:
            checks.append((
                name,
                sum(1 for devise in values if _devise_invalide(devise)),
                message,
            ))

        issues = 0
        self.stdout.write("Audit legacy PredictNeed IA (lecture seule)")

        for name, count, message in checks:
            status = "OK" if count == 0 else "A_VERIFIER"
            self.stdout.write(f"- {status} {name}: {count} ({message})")
            if count:
                issues += count

        if options["fail_on_issues"] and issues:
            raise CommandError(
                f"{issues} point(s) legacy nécessitent une revue."
            )
