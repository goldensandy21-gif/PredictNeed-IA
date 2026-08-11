from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from .ad_performance import calculer_performance_campagne
from .models import (
    CampagneExterne,
    ClientProfessionnel,
    CompteConnecteExterne,
    MesureCampagneExterne,
    SiteClient,
)


class GoogleAdsReportingPhase4CTests(TestCase):

    def setUp(self):
        User = get_user_model()

        self.user = User.objects.create_user(
            username="google-reporting",
            email="google-reporting@example.com",
            password="Test-2026-solide!",
        )

        self.client_pro = ClientProfessionnel.objects.create(
            utilisateur=self.user,
            nom_entreprise="Entreprise Reporting",
            statut_abonnement="actif",
        )

        self.site = SiteClient.objects.create(
            client=self.client_pro,
            nom_site="Site Reporting",
            domaine="reporting.example",
            actif=True,
            module_publicite_actif=True,
        )

        self.compte = CompteConnecteExterne.objects.create(
            client=self.client_pro,
            site=self.site,
            plateforme="google_ads",
            nom_compte="Google Ads 123",
            identifiant_externe="1234567890",
            statut="connecte",
        )

        self.campagne = CampagneExterne.objects.create(
            compte=self.compte,
            site=self.site,
            plateforme="google_ads",
            source_donnees="api_regie",
            identifiant_externe="777001",
            nom="Campagne historique",
            statut="REMOVED",
            devise="EUR",
            donnees_brutes={
                "status": "REMOVED",
                "advertising_channel_type": "SMART",
                "budget_amount": "1.10",
                "budget_period": "DAILY",
                "bidding_strategy_type": "TARGET_SPEND",
            },
        )

        MesureCampagneExterne.objects.create(
            campagne=self.campagne,
            compte=self.compte,
            site=self.site,
            plateforme="google_ads",
            date=date(2022, 10, 1),
            impressions=12926,
            clics=484,
            conversions=Decimal("2.0000"),
            depense=Decimal("79.88"),
            devise="EUR",
            donnees_brutes={
                "granularite": "mensuelle",
                "conversions_value": "180.50",
                "all_conversions": "2.0000",
                "all_conversions_value": "180.50",
            },
        )

    def test_reporting_google_ads_enrichi(self):
        performance = calculer_performance_campagne(
            self.campagne
        )

        self.assertEqual(
            performance["impressions"],
            12926,
        )

        self.assertEqual(
            performance["clics"],
            484,
        )

        self.assertEqual(
            performance["valeur_conversions_regie"],
            Decimal("180.5000"),
        )

        self.assertEqual(
            performance["cout_par_conversion_regie"],
            Decimal("39.94"),
        )

        self.assertEqual(
            performance["roas_regie"],
            Decimal("2.26"),
        )

        self.assertEqual(
            performance["budget_label"],
            "Budget moyen / jour",
        )

        self.assertEqual(
            performance["strategie_encheres"],
            "Dépenses cibles",
        )
