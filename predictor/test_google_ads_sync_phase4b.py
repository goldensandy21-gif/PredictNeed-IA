from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import signing
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .google_ads_api import lister_performances_campagnes
from .google_ads_sync import synchroniser_compte_google_ads
from .models import (
    CampagneExterne,
    ClientProfessionnel,
    CompteConnecteExterne,
    JournalSynchronisationConnecteur,
    MesureCampagneExterne,
    SiteClient,
)


FAKE_CONNECTORS = {
    "google_ads": {
        "nom": "Google Ads",
        "description": "Test Google Ads",
        "client_id": "client-test",
        "client_secret": "secret-test",
        "developer_token": "developer-token-test",
        "login_customer_id": "",
        "api_version": "v25",
        "auth_url": "https://accounts.example.test/auth",
        "token_url": "https://accounts.example.test/token",
        "scopes": ["https://www.googleapis.com/auth/adwords"],
        "variables_requises": [
            "GOOGLE_ADS_CLIENT_ID",
            "GOOGLE_ADS_CLIENT_SECRET",
            "GOOGLE_ADS_DEVELOPER_TOKEN",
        ],
        "variables_optionnelles": [],
    },
}


@override_settings(PREDICTNEED_EXTERNAL_CONNECTORS=FAKE_CONNECTORS)
class GoogleAdsNativeSyncTests(TestCase):

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="google-sync",
            email="google-sync@example.com",
            password="MotDePasse-Solide-2026!",
        )
        self.client_pro = ClientProfessionnel.objects.create(
            utilisateur=self.user,
            nom_entreprise="Entreprise Google Sync",
            statut_abonnement="actif",
        )
        self.site = SiteClient.objects.create(
            client=self.client_pro,
            nom_site="Site Google Sync",
            domaine="google-sync.example",
            actif=True,
            module_connecteurs_actif=True,
        )
        self.compte = CompteConnecteExterne.objects.create(
            client=self.client_pro,
            site=self.site,
            plateforme="google_ads",
            nom_compte="Google Ads Sync",
            identifiant_externe="1234567890",
            statut="connecte",
            access_token_signe=signing.dumps(
                "access-test",
                salt="predictneed-connecteur-token",
            ),
            refresh_token_signe=signing.dumps(
                "refresh-test",
                salt="predictneed-connecteur-token",
            ),
            expires_at=timezone.now() + timedelta(hours=1),
            configuration={
                "customer_id": "1234567890",
                "login_customer_id": "9999999999",
                "devise": "EUR",
            },
        )

    @patch("predictor.google_ads_api.rechercher")
    def test_campaign_report_uses_daily_metrics(self, rechercher):
        rechercher.return_value = []
        lister_performances_campagnes(
            "access-token",
            "1234567890",
            login_customer_id="9999999999",
            periode="LAST_30_DAYS",
        )
        query = rechercher.call_args.args[2]
        self.assertIn("segments.date", query)
        self.assertIn("campaign.id", query)
        self.assertIn("metrics.impressions", query)
        self.assertIn("metrics.clicks", query)
        self.assertIn("metrics.conversions", query)
        self.assertIn("metrics.cost_micros", query)
        self.assertIn("segments.date DURING LAST_30_DAYS", query)
        self.assertEqual(
            rechercher.call_args.kwargs["login_customer_id"],
            "9999999999",
        )

    @patch("predictor.google_ads_sync.lister_performances_campagnes")
    def test_sync_creates_native_campaign_and_daily_measure(self, report):
        report.return_value = [{
            "campaign": {
                "id": "555001",
                "name": "Campagne Search",
                "status": "ENABLED",
                "advertisingChannelType": "SEARCH",
            },
            "segments": {"date": "2026-08-08"},
            "metrics": {
                "impressions": "1200",
                "clicks": "84",
                "conversions": 4.5,
                "costMicros": "123450000",
            },
        }]
        resultat = synchroniser_compte_google_ads(self.compte)
        self.assertEqual(resultat["campagnes"], 1)
        self.assertEqual(resultat["mesures"], 1)

        campagne = CampagneExterne.objects.get(
            compte=self.compte,
            identifiant_externe="555001",
        )
        self.assertEqual(campagne.source_donnees, "api_regie")
        self.assertEqual(campagne.site, self.site)
        self.assertEqual(campagne.conversions, Decimal("4.5000"))
        self.assertEqual(campagne.depense, Decimal("123.45"))

        mesure = MesureCampagneExterne.objects.get(
            campagne=campagne,
            date=date(2026, 8, 8),
        )
        self.assertEqual(mesure.impressions, 1200)
        self.assertEqual(mesure.clics, 84)
        self.assertEqual(mesure.conversions, Decimal("4.5000"))
        self.assertEqual(mesure.depense, Decimal("123.45"))

    @patch("predictor.google_ads_sync.lister_performances_campagnes")
    def test_resync_same_day_updates_without_duplicate(self, report):
        report.return_value = [{
            "campaign": {"id": "555002", "name": "Campagne évolutive", "status": "ENABLED"},
            "segments": {"date": "2026-08-08"},
            "metrics": {
                "impressions": "100",
                "clicks": "10",
                "conversions": "1.25",
                "costMicros": "10000000",
            },
        }]
        synchroniser_compte_google_ads(self.compte)

        report.return_value[0]["metrics"] = {
            "impressions": "250",
            "clicks": "20",
            "conversions": "2.75",
            "costMicros": "22500000",
        }
        synchroniser_compte_google_ads(self.compte)

        campagne = CampagneExterne.objects.get(
            compte=self.compte,
            identifiant_externe="555002",
        )
        self.assertEqual(
            MesureCampagneExterne.objects.filter(campagne=campagne).count(),
            1,
        )
        campagne.refresh_from_db()
        self.assertEqual(campagne.impressions, 250)
        self.assertEqual(campagne.clics, 20)
        self.assertEqual(campagne.conversions, Decimal("2.7500"))
        self.assertEqual(campagne.depense, Decimal("22.50"))

    @patch("predictor.google_ads_sync.lister_performances_campagnes")
    def test_sync_accumulates_multiple_days(self, report):
        report.return_value = [
            {
                "campaign": {"id": "555003", "name": "Campagne 2 jours", "status": "ENABLED"},
                "segments": {"date": "2026-08-07"},
                "metrics": {
                    "impressions": "100",
                    "clicks": "10",
                    "conversions": "1.25",
                    "costMicros": "10000000",
                },
            },
            {
                "campaign": {"id": "555003", "name": "Campagne 2 jours", "status": "ENABLED"},
                "segments": {"date": "2026-08-08"},
                "metrics": {
                    "impressions": "200",
                    "clicks": "20",
                    "conversions": "2.50",
                    "costMicros": "20000000",
                },
            },
        ]
        synchroniser_compte_google_ads(self.compte)
        campagne = CampagneExterne.objects.get(
            compte=self.compte,
            identifiant_externe="555003",
        )
        self.assertEqual(campagne.impressions, 300)
        self.assertEqual(campagne.clics, 30)
        self.assertEqual(campagne.conversions, Decimal("3.7500"))
        self.assertEqual(campagne.depense, Decimal("30.00"))

    @patch(
        "predictor.views.synchroniser_compte_google_ads",
        return_value={"campagnes": 2, "mesures": 15, "periode": "LAST_30_DAYS"},
    )
    @patch("predictor.views.synchroniser_compte_depuis_utm")
    def test_view_uses_native_google_sync_not_utm(self, utm_sync, google_sync):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("synchroniser_compte_connecteur", args=[self.compte.id])
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response["Location"],
            f"{reverse('module_connecteurs')}?site={self.site.id}",
        )
        google_sync.assert_called_once_with(
            self.compte,
            periode="LAST_30_DAYS",
        )
        utm_sync.assert_not_called()

    @patch("predictor.google_ads_sync.lister_performances_campagnes")
    def test_sync_writes_success_journal(self, report):
        report.return_value = []
        resultat = synchroniser_compte_google_ads(self.compte)
        self.compte.refresh_from_db()
        journal = (
            JournalSynchronisationConnecteur.objects
            .filter(compte=self.compte)
            .latest("date_creation")
        )
        self.assertEqual(resultat["campagnes"], 0)
        self.assertEqual(journal.statut, "succes")
        self.assertEqual(journal.details["source"], "google_ads_api")
        self.assertIn("Google Ads", self.compte.dernier_message)
