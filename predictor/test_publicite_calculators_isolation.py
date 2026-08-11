from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from .linkedin_ads_performance import (
    calculer_performance_linkedin_ads,
)
from .meta_ads_performance import (
    calculer_performance_meta_ads,
)
from .tiktok_ads_performance import (
    calculer_performance_tiktok_ads,
)
from .models import (
    CampagneExterne,
    ClientProfessionnel,
    CompteConnecteExterne,
    MesureCampagneExterne,
    SiteClient,
)


class PubliciteCalculatorsIsolationTests(TestCase):

    def setUp(self):
        User = get_user_model()

        self.user = User.objects.create_user(
            username="ads-calcul-isolation",
            password="Test-2026-solide!",
        )

        self.client_pro = ClientProfessionnel.objects.create(
            utilisateur=self.user,
            nom_entreprise="Calculs Publicité",
            statut_abonnement="actif",
        )

        self.site = SiteClient.objects.create(
            client=self.client_pro,
            nom_site="Site Calculs",
            domaine="calculs.example",
            actif=True,
            module_publicite_actif=True,
        )

        self.comptes = {}
        self.campagnes = {}

        for plateforme in (
            "google_ads",
            "meta_ads",
            "tiktok_ads",
            "linkedin_ads",
        ):
            compte = CompteConnecteExterne.objects.create(
                client=self.client_pro,
                site=self.site,
                plateforme=plateforme,
                nom_compte=f"Compte {plateforme}",
                identifiant_externe=f"account-{plateforme}",
                statut="connecte",
            )

            campagne = CampagneExterne.objects.create(
                compte=compte,
                site=self.site,
                plateforme=plateforme,
                identifiant_externe=f"campaign-{plateforme}",
                nom=f"Campagne {plateforme}",
                devise="EUR",
            )

            self.comptes[plateforme] = compte
            self.campagnes[plateforme] = campagne

    def test_calculateurs_refusent_les_campagnes_etrangeres(self):
        with self.assertRaises(ValueError):
            calculer_performance_meta_ads(
                self.campagnes["google_ads"]
            )

        with self.assertRaises(ValueError):
            calculer_performance_tiktok_ads(
                self.campagnes["meta_ads"]
            )

        with self.assertRaises(ValueError):
            calculer_performance_linkedin_ads(
                self.campagnes["tiktok_ads"]
            )

    def test_meta_ignore_une_mesure_dune_autre_regie(self):
        campagne = self.campagnes["meta_ads"]
        compte = self.comptes["meta_ads"]

        aujourd_hui = timezone.localdate()
        hier = aujourd_hui - timedelta(days=1)

        MesureCampagneExterne.objects.create(
            campagne=campagne,
            compte=compte,
            site=self.site,
            plateforme="meta_ads",
            date=aujourd_hui,
            impressions=100,
            clics=10,
            conversions=Decimal("2"),
            depense=Decimal("20.00"),
            devise="EUR",
        )

        # Mesure volontairement incohérente.
        MesureCampagneExterne.objects.create(
            campagne=campagne,
            compte=compte,
            site=self.site,
            plateforme="google_ads",
            date=hier,
            impressions=9999,
            clics=999,
            conversions=Decimal("99"),
            depense=Decimal("999.00"),
            devise="EUR",
        )

        performance = calculer_performance_meta_ads(
            campagne,
            date_debut=hier,
            date_fin=aujourd_hui,
        )

        self.assertEqual(performance["impressions"], 100)
        self.assertEqual(performance["clics"], 10)
        self.assertEqual(
            performance["conversions_regie"],
            Decimal("2.0000"),
        )
        self.assertEqual(
            performance["depense"],
            Decimal("20.00"),
        )
