from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .external_connectors import signer_token
from .meta_ads_sync import synchroniser_compte_meta_ads
from .models import (
    CampagneExterne,
    ClientProfessionnel,
    CompteConnecteExterne,
    JournalSynchronisationConnecteur,
    MesureCampagneExterne,
    SiteClient,
)


FAKE_CONNECTORS = {
    "meta_ads": {
        "nom": "Meta Ads",
        "description": "Test Meta Ads",
        "client_id": "client-test",
        "client_secret": "secret-test",
        "api_version": "v25.0",
        "auth_url": "https://facebook.example.test/auth",
        "token_url": "https://facebook.example.test/token",
        "scopes": ["ads_read", "business_management"],
        "variables_requises": [
            "META_ADS_CLIENT_ID",
            "META_ADS_CLIENT_SECRET",
        ],
        "variables_optionnelles": [],
    },
}


@override_settings(PREDICTNEED_EXTERNAL_CONNECTORS=FAKE_CONNECTORS)
class MetaAdsNativeSyncTests(TestCase):

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="meta-sync",
            email="meta-sync@example.com",
            password="MotDePasse-Solide-2026!",
        )
        self.client_pro = ClientProfessionnel.objects.create(
            utilisateur=self.user,
            nom_entreprise="Entreprise Meta Sync",
            statut_abonnement="actif",
        )
        self.site = SiteClient.objects.create(
            client=self.client_pro,
            nom_site="Site Meta Sync",
            domaine="meta-sync.example",
            actif=True,
            module_connecteurs_actif=True,
        )
        self.compte = CompteConnecteExterne.objects.create(
            client=self.client_pro,
            site=self.site,
            plateforme="meta_ads",
            nom_compte="Meta Ads Sync",
            identifiant_externe="act_123456789",
            statut="connecte",
            access_token_signe=signer_token("access-meta"),
            expires_at=timezone.now() + timedelta(hours=1),
            configuration={
                "account_id": "123456789",
                "graph_id": "act_123456789",
                "devise": "EUR",
            },
        )

    @patch("predictor.meta_ads_sync.lister_performances_campagnes_meta")
    def test_sync_creates_native_campaign_and_daily_measure(
        self,
        report,
    ):
        report.return_value = [{
            "campaign_id": "777001",
            "campaign_name": "Campagne Meta Leads",
            "date_start": "2026-08-08",
            "date_stop": "2026-08-08",
            "impressions": "1200",
            "clicks": "84",
            "spend": "123.45",
            "account_currency": "EUR",
            "actions": [
                {"action_type": "link_click", "value": "84"},
                {"action_type": "lead", "value": "4"},
            ],
        }]

        resultat = synchroniser_compte_meta_ads(self.compte)

        self.assertEqual(resultat["campagnes"], 1)
        self.assertEqual(resultat["mesures"], 1)
        report.assert_called_once_with(
            "access-meta",
            "123456789",
            periode="LAST_30_DAYS",
        )

        campagne = CampagneExterne.objects.get(
            compte=self.compte,
            identifiant_externe="777001",
        )
        self.assertEqual(campagne.source_donnees, "api_regie")
        self.assertEqual(campagne.site, self.site)
        self.assertEqual(campagne.plateforme, "meta_ads")
        self.assertEqual(campagne.conversions, Decimal("4.0000"))
        self.assertEqual(campagne.depense, Decimal("123.45"))

        mesure = MesureCampagneExterne.objects.get(
            campagne=campagne,
            date=date(2026, 8, 8),
        )
        self.assertEqual(mesure.impressions, 1200)
        self.assertEqual(mesure.clics, 84)
        self.assertEqual(mesure.conversions, Decimal("4.0000"))
        self.assertEqual(mesure.depense, Decimal("123.45"))

    @patch("predictor.meta_ads_sync.lister_performances_campagnes_meta")
    def test_resync_same_day_updates_without_duplicate(
        self,
        report,
    ):
        report.return_value = [{
            "campaign_id": "777002",
            "campaign_name": "Campagne Meta évolutive",
            "date_start": "2026-08-08",
            "impressions": "100",
            "clicks": "10",
            "spend": "10.00",
            "account_currency": "EUR",
            "conversions": [{"value": "1.25"}],
        }]
        synchroniser_compte_meta_ads(self.compte)

        report.return_value[0].update({
            "impressions": "250",
            "clicks": "20",
            "spend": "22.50",
            "conversions": [{"value": "2.75"}],
        })
        synchroniser_compte_meta_ads(self.compte)

        campagne = CampagneExterne.objects.get(
            compte=self.compte,
            identifiant_externe="777002",
        )
        self.assertEqual(
            MesureCampagneExterne.objects.filter(
                campagne=campagne,
            ).count(),
            1,
        )
        campagne.refresh_from_db()
        self.assertEqual(campagne.impressions, 250)
        self.assertEqual(campagne.clics, 20)
        self.assertEqual(campagne.conversions, Decimal("2.7500"))
        self.assertEqual(campagne.depense, Decimal("22.50"))

    @patch("predictor.meta_ads_sync.lister_performances_campagnes_meta")
    def test_sync_writes_success_journal(self, report):
        report.return_value = []

        resultat = synchroniser_compte_meta_ads(self.compte)

        self.compte.refresh_from_db()
        journal = (
            JournalSynchronisationConnecteur.objects
            .filter(compte=self.compte)
            .latest("date_creation")
        )
        self.assertEqual(resultat["campagnes"], 0)
        self.assertEqual(journal.statut, "succes")
        self.assertEqual(journal.details["source"], "meta_ads_api")
        self.assertIn("Meta Ads", self.compte.dernier_message)

    def test_expired_token_is_rejected(self):
        self.compte.expires_at = timezone.now() - timedelta(minutes=1)
        self.compte.save(update_fields=["expires_at"])

        with self.assertRaises(ValueError):
            synchroniser_compte_meta_ads(self.compte)

    @patch(
        "predictor.views.synchroniser_compte_meta_ads",
        return_value={
            "campagnes": 2,
            "mesures": 15,
            "periode": "LAST_30_DAYS",
        },
    )
    @patch("predictor.views.synchroniser_compte_depuis_utm")
    def test_view_uses_native_meta_sync_not_utm(
        self,
        utm_sync,
        meta_sync,
    ):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse(
                "synchroniser_compte_connecteur",
                args=[self.compte.id],
            )
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response["Location"],
            f"{reverse('module_connecteurs')}?site={self.site.id}",
        )
        meta_sync.assert_called_once_with(
            self.compte,
            periode="LAST_30_DAYS",
        )
        utm_sync.assert_not_called()
