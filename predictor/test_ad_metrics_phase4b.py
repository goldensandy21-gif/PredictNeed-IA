from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from .ad_metrics import enregistrer_mesure_campagne_native
from .external_connectors import synchroniser_compte_depuis_utm
from .models import (
    CampagneExterne,
    ClientProfessionnel,
    CompteConnecteExterne,
    MesureCampagneExterne,
    SessionVisiteur,
    SiteClient,
)


class MesuresRegiesPhase4BTests(TestCase):

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="ads-metrics",
            email="ads-metrics@example.com",
            password="MotDePasse-Solide-2026!",
        )
        self.client_pro = ClientProfessionnel.objects.create(
            utilisateur=self.user,
            nom_entreprise="Entreprise Ads",
            statut_abonnement="actif",
        )
        self.site = SiteClient.objects.create(
            client=self.client_pro,
            nom_site="Site Ads",
            domaine="ads.example",
            actif=True,
            module_connecteurs_actif=True,
            module_publicite_actif=True,
        )
        self.compte = CompteConnecteExterne.objects.create(
            client=self.client_pro,
            site=self.site,
            plateforme="google_ads",
            nom_compte="Google Ads Test",
            identifiant_externe="1234567890",
            statut="connecte",
        )
        self.campagne = CampagneExterne.objects.create(
            compte=self.compte,
            site=self.site,
            plateforme="google_ads",
            identifiant_externe="campaign-1",
            nom="Campagne native",
            source_donnees="api_regie",
        )

    def test_mesure_native_cree_historique_et_totaux(self):
        enregistrer_mesure_campagne_native(
            self.campagne,
            date=date(2026, 8, 8),
            impressions=1000,
            clics=80,
            conversions="4.5",
            depense="120.40",
            devise="EUR",
        )

        self.campagne.refresh_from_db()
        mesure = MesureCampagneExterne.objects.get(
            campagne=self.campagne,
            date=date(2026, 8, 8),
        )

        self.assertEqual(mesure.impressions, 1000)
        self.assertEqual(mesure.clics, 80)
        self.assertEqual(
            mesure.conversions,
            Decimal("4.5000"),
        )
        self.assertEqual(
            mesure.depense,
            Decimal("120.40"),
        )
        self.assertEqual(
            self.campagne.source_donnees,
            "api_regie",
        )
        self.assertEqual(self.campagne.impressions, 1000)
        self.assertEqual(self.campagne.clics, 80)
        self.assertEqual(
            self.campagne.depense,
            Decimal("120.40"),
        )

    def test_meme_jour_met_a_jour_sans_doublon(self):
        enregistrer_mesure_campagne_native(
            self.campagne,
            date=date(2026, 8, 8),
            impressions=100,
            clics=10,
            depense="5.00",
        )
        enregistrer_mesure_campagne_native(
            self.campagne,
            date=date(2026, 8, 8),
            impressions=250,
            clics=25,
            depense="12.50",
        )

        self.assertEqual(
            MesureCampagneExterne.objects.filter(
                campagne=self.campagne,
            ).count(),
            1,
        )

        self.campagne.refresh_from_db()
        self.assertEqual(self.campagne.impressions, 250)
        self.assertEqual(self.campagne.clics, 25)
        self.assertEqual(
            self.campagne.depense,
            Decimal("12.50"),
        )

    def test_plusieurs_jours_sont_additionnes(self):
        enregistrer_mesure_campagne_native(
            self.campagne,
            date=date(2026, 8, 7),
            impressions=500,
            clics=30,
            conversions="2",
            depense="40",
        )
        enregistrer_mesure_campagne_native(
            self.campagne,
            date=date(2026, 8, 8),
            impressions=700,
            clics=50,
            conversions="3",
            depense="60",
        )

        self.campagne.refresh_from_db()

        self.assertEqual(self.campagne.impressions, 1200)
        self.assertEqual(self.campagne.clics, 80)
        self.assertEqual(self.campagne.conversions, 5)
        self.assertEqual(
            self.campagne.depense,
            Decimal("100.00"),
        )

    def test_incoherence_site_compte_est_refusee(self):
        autre_site = SiteClient.objects.create(
            client=self.client_pro,
            nom_site="Autre site",
            domaine="autre.example",
            actif=True,
        )
        campagne_invalide = CampagneExterne.objects.create(
            compte=self.compte,
            site=autre_site,
            plateforme="google_ads",
            identifiant_externe="campaign-invalid",
            nom="Campagne invalide",
        )

        with self.assertRaises(ValueError):
            enregistrer_mesure_campagne_native(
                campagne_invalide,
                date=date(2026, 8, 8),
                impressions=100,
            )

        self.assertFalse(
            MesureCampagneExterne.objects.filter(
                campagne=campagne_invalide,
            ).exists()
        )

    def test_rapprochement_utm_reste_identifie_comme_utm(self):
        SessionVisiteur.objects.create(
            site=self.site,
            session_id="utm-1",
            utm_source="google",
            utm_medium="cpc",
            utm_campaign="campagne-utm",
        )

        total = synchroniser_compte_depuis_utm(
            self.compte,
            SiteClient.objects.filter(pk=self.site.pk),
        )

        self.assertEqual(total, 1)

        campagne = CampagneExterne.objects.get(
            compte=self.compte,
            utm_campaign="campagne-utm",
        )

        self.assertEqual(
            campagne.source_donnees,
            "utm_predictneed",
        )
        self.assertEqual(
            campagne.donnees_brutes["origine"],
            "utm_predictneed",
        )
        self.assertFalse(
            MesureCampagneExterne.objects.filter(
                campagne=campagne,
            ).exists()
        )
