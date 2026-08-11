from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import signing
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .google_ads_api import (
    lister_actions_conversion_google_ads,
    lister_campagnes_google_ads,
    lister_performances_campagnes,
    lister_performances_campagnes_intervalle,
    lister_performances_campagnes_mensuelles,
)
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
                "google_ads_historique_37_mois_importe": True,
                "google_ads_historique_mensuel_11_ans_importe": True,
            },
        )


        self.campaign_inventory_patcher = patch(
            "predictor.google_ads_sync.lister_campagnes_google_ads",
            return_value=[],
        )
        self.campaign_inventory = (
            self.campaign_inventory_patcher.start()
        )
        self.addCleanup(
            self.campaign_inventory_patcher.stop
        )

        self.conversion_actions_patcher = patch(
            "predictor.google_ads_sync."
            "lister_actions_conversion_google_ads",
            return_value=[],
        )
        self.conversion_actions = (
            self.conversion_actions_patcher.start()
        )
        self.addCleanup(
            self.conversion_actions_patcher.stop
        )

        self.conversion_history_patcher = patch(
            "predictor.google_ads_sync."
            "lister_performances_actions_conversion_mensuelles",
            return_value=[],
        )
        self.conversion_history = (
            self.conversion_history_patcher.start()
        )
        self.addCleanup(
            self.conversion_history_patcher.stop
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


    @patch("predictor.google_ads_api.rechercher")
    def test_campaign_inventory_is_independent_from_metrics(
        self,
        rechercher,
    ):
        rechercher.return_value = []

        lister_campagnes_google_ads(
            "access-token",
            "1234567890",
            login_customer_id="9999999999",
        )

        query = rechercher.call_args.args[2]

        self.assertIn("campaign.id", query)
        self.assertIn("campaign.name", query)
        self.assertIn("campaign.status", query)
        self.assertIn("campaign.primary_status", query)
        self.assertIn("campaign.serving_status", query)
        self.assertIn(
            "campaign.advertising_channel_type",
            query,
        )
        self.assertIn(
            "campaign_budget.amount_micros",
            query,
        )

        self.assertNotIn("segments.date", query)
        self.assertNotIn("metrics.", query)
        self.assertNotIn(
            "campaign.status != 'REMOVED'",
            query,
        )


    @patch(
        "predictor.google_ads_sync."
        "lister_performances_campagnes"
    )
    def test_sync_imports_campaign_without_daily_metrics(
        self,
        report,
    ):
        self.campaign_inventory.return_value = [{
            "campaign": {
                "id": "777001",
                "name": "Ancienne Performance Max",
                "status": "REMOVED",
                "primaryStatus": "REMOVED",
                "servingStatus": "NONE",
                "advertisingChannelType": "PERFORMANCE_MAX",
                "advertisingChannelSubType": "",
                "startDateTime": "2024-01-01 00:00:00",
                "endDateTime": "2024-06-30 23:59:59",
                "optimizationScore": None,
                "biddingStrategyType": (
                    "MAXIMIZE_CONVERSION_VALUE"
                ),
                "biddingStrategySystemStatus": "PAUSED",
            },
            "campaignBudget": {
                "amountMicros": "1000000",
                "status": "ENABLED",
            },
        }]

        report.return_value = []

        resultat = synchroniser_compte_google_ads(
            self.compte
        )

        self.assertEqual(resultat["campagnes"], 1)
        self.assertEqual(resultat["mesures"], 0)

        campagne = CampagneExterne.objects.get(
            compte=self.compte,
            identifiant_externe="777001",
        )

        self.assertEqual(
            campagne.nom,
            "Ancienne Performance Max",
        )
        self.assertEqual(
            campagne.statut,
            "REMOVED",
        )
        self.assertEqual(
            campagne.impressions,
            0,
        )
        self.assertEqual(
            campagne.clics,
            0,
        )
        self.assertEqual(
            campagne.depense,
            Decimal("0.00"),
        )

        brut = campagne.donnees_brutes

        self.assertEqual(
            brut["primary_status"],
            "REMOVED",
        )
        self.assertEqual(
            brut["serving_status"],
            "NONE",
        )
        self.assertEqual(
            brut["advertising_channel_type"],
            "PERFORMANCE_MAX",
        )
        self.assertEqual(
            brut["budget_amount"],
            "1.00",
        )


    @patch("predictor.google_ads_api.rechercher")
    def test_campaign_report_accepts_custom_history_range(
        self,
        rechercher,
    ):
        rechercher.return_value = []

        lister_performances_campagnes_intervalle(
            "access-token",
            "1234567890",
            login_customer_id="9999999999",
            date_debut=date(2024, 1, 1),
            date_fin=date(2024, 12, 31),
        )

        query = rechercher.call_args.args[2]

        self.assertIn(
            "segments.date BETWEEN "
            "'2024-01-01' AND '2024-12-31'",
            query,
        )

        self.assertIn(
            "metrics.conversions_value",
            query,
        )

        self.assertIn(
            "metrics.cost_micros",
            query,
        )


    @patch(
        "predictor.google_ads_sync."
        "lister_performances_campagnes"
    )
    @patch(
        "predictor.google_ads_sync."
        "lister_performances_campagnes_intervalle"
    )
    def test_first_sync_imports_37_month_history_once(
        self,
        historique,
        recent,
    ):
        configuration = dict(
            self.compte.configuration
        )

        configuration.pop(
            "google_ads_historique_37_mois_importe",
            None,
        )

        self.compte.configuration = configuration
        self.compte.save(
            update_fields=[
                "configuration",
                "date_mise_a_jour",
            ]
        )

        historique.return_value = []
        recent.return_value = []

        resultat = synchroniser_compte_google_ads(
            self.compte
        )

        historique.assert_called_once()
        recent.assert_not_called()

        self.compte.refresh_from_db()

        self.assertTrue(
            self.compte.configuration[
                "google_ads_historique_37_mois_importe"
            ]
        )

        self.assertIn(
            "google_ads_historique_37_mois_debut",
            self.compte.configuration,
        )

        self.assertIn(
            "google_ads_historique_37_mois_fin",
            self.compte.configuration,
        )

        self.assertIn(
            "HISTORIQUE_37_MOIS",
            resultat["periode"],
        )


    @patch("predictor.google_ads_api.rechercher")
    def test_monthly_history_query_uses_month_segment(
        self,
        rechercher,
    ):
        rechercher.return_value = []

        lister_performances_campagnes_mensuelles(
            "access-token",
            "1234567890",
            login_customer_id="9999999999",
            date_debut=date(2016, 1, 1),
            date_fin=date(2023, 6, 1),
        )

        query = rechercher.call_args.args[2]

        self.assertIn(
            "segments.month",
            query,
        )

        self.assertNotIn(
            "segments.date,",
            query,
        )

        self.assertIn(
            "segments.month BETWEEN "
            "'2016-01-01' AND '2023-06-01'",
            query,
        )


    @patch(
        "predictor.google_ads_sync."
        "lister_performances_campagnes"
    )
    @patch(
        "predictor.google_ads_sync."
        "lister_performances_campagnes_mensuelles"
    )
    def test_second_history_sync_uses_monthly_data(
        self,
        mensuel,
        recent,
    ):
        configuration = dict(
            self.compte.configuration
        )

        configuration[
            "google_ads_historique_37_mois_importe"
        ] = True

        configuration[
            "google_ads_historique_37_mois_debut"
        ] = "2023-08-01"

        configuration.pop(
            "google_ads_historique_mensuel_11_ans_importe",
            None,
        )

        self.compte.configuration = configuration

        self.compte.save(
            update_fields=[
                "configuration",
                "date_mise_a_jour",
            ]
        )

        mensuel.return_value = []
        recent.return_value = []

        resultat = synchroniser_compte_google_ads(
            self.compte
        )

        mensuel.assert_called_once()
        recent.assert_not_called()

        appel_mensuel = mensuel.call_args.kwargs
        self.assertEqual(
            appel_mensuel["date_fin"],
            date(2023, 7, 1),
        )

        self.compte.refresh_from_db()

        self.assertTrue(
            self.compte.configuration[
                "google_ads_historique_mensuel_11_ans_importe"
            ]
        )

        self.assertIn(
            "HISTORIQUE_MENSUEL_11_ANS",
            resultat["periode"],
        )


    @patch("predictor.google_ads_api.rechercher")
    def test_conversion_actions_query_reads_value_settings(
        self,
        rechercher,
    ):
        rechercher.return_value = []

        lister_actions_conversion_google_ads(
            "access-token",
            "1234567890",
            login_customer_id="9999999999",
        )

        query = rechercher.call_args.args[2]

        self.assertIn(
            "conversion_action.primary_for_goal",
            query,
        )

        self.assertIn(
            "conversion_action.value_settings.default_value",
            query,
        )

        self.assertIn(
            "conversion_action.category",
            query,
        )


    @patch(
        "predictor.google_ads_sync."
        "lister_performances_campagnes",
        return_value=[],
    )
    def test_sync_stores_conversion_action_diagnostic(
        self,
        recent,
    ):
        configuration = dict(
            self.compte.configuration
        )

        configuration.pop(
            "google_ads_actions_conversion_historique_importe",
            None,
        )

        self.compte.configuration = configuration
        self.compte.save()

        self.conversion_actions.return_value = [{
            "conversionAction": {
                "resourceName": (
                    "customers/1234567890/"
                    "conversionActions/123"
                ),
                "id": "123",
                "name": "Achat",
                "status": "ENABLED",
                "category": "PURCHASE",
                "type": "WEBPAGE",
                "origin": "WEBSITE",
                "primaryForGoal": True,
                "countingType": "MANY_PER_CLICK",
                "valueSettings": {
                    "defaultValue": 0,
                    "defaultCurrencyCode": "EUR",
                    "alwaysUseDefaultValue": False,
                },
            }
        }]

        self.conversion_history.return_value = [{
            "campaign": {
                "id": "555001",
                "name": "Campagne historique",
            },
            "segments": {
                "month": "2022-10-01",
                "conversionAction": (
                    "customers/1234567890/"
                    "conversionActions/123"
                ),
                "conversionActionName": "Achat",
                "conversionActionCategory": "PURCHASE",
            },
            "metrics": {
                "conversions": "2",
                "conversionsValue": "0",
                "allConversions": "2",
                "allConversionsValue": "0",
            },
        }]

        synchroniser_compte_google_ads(
            self.compte
        )

        self.compte.refresh_from_db()

        actions = self.compte.configuration[
            "google_ads_actions_conversion"
        ]

        self.assertEqual(len(actions), 1)
        self.assertEqual(
            actions[0]["name"],
            "Achat",
        )
        self.assertTrue(
            actions[0]["primary_for_goal"]
        )
        self.assertEqual(
            actions[0]["conversions"],
            "2",
        )
        self.assertEqual(
            actions[0]["conversions_value"],
            "0",
        )
