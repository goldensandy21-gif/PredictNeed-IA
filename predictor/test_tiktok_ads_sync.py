from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .external_connectors import signer_token
from .models import (
    CampagneExterne,
    ClientProfessionnel,
    CompteConnecteExterne,
    JournalSynchronisationConnecteur,
    MesureCampagneExterne,
    SiteClient,
)
from .tiktok_ads_sync import synchroniser_compte_tiktok_ads


FAKE_CONNECTORS = {
    "tiktok_ads": {
        "nom": "TikTok Ads",
        "description": "Test TikTok Ads",
        "client_id": "app-id",
        "client_secret": "secret",
        "api_version": "v1.3",
        "base_url": "https://business-api.tiktok.com/open_api",
        "auth_url": "https://ads.tiktok.com/marketing_api/auth",
        "token_url": (
            "https://business-api.tiktok.com/open_api/"
            "v1.3/oauth2/access_token/"
        ),
        "scopes": [],
    },
}

TEST_STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}


@override_settings(
    PREDICTNEED_EXTERNAL_CONNECTORS=FAKE_CONNECTORS,
    STORAGES=TEST_STORAGES,
)
class TikTokAdsSyncTests(TestCase):

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="tiktok-sync",
            email="tiktok-sync@example.com",
            password="MotDePasse-Solide-2026!",
        )
        self.client_pro = ClientProfessionnel.objects.create(
            utilisateur=self.user,
            nom_entreprise="TikTok Sync",
            statut_abonnement="actif",
        )
        self.site = SiteClient.objects.create(
            client=self.client_pro,
            nom_site="TikTok Sync Site",
            domaine="tiktok-sync.example",
            actif=True,
            module_connecteurs_actif=True,
        )
        self.compte = CompteConnecteExterne.objects.create(
            client=self.client_pro,
            site=self.site,
            plateforme="tiktok_ads",
            identifiant_externe="123",
            nom_compte="Advertiser TikTok",
            statut="connecte",
            access_token_signe=signer_token("access-tiktok"),
            refresh_token_signe=signer_token("refresh-tiktok"),
            expires_at=timezone.now() + timedelta(hours=1),
            configuration={
                "source": "oauth_tiktok_ads",
                "advertiser_id": "123",
                "devise": "EUR",
            },
        )

    def _campaigns(self):
        return [
            {
                "campaign_id": "555",
                "nom": "Campagne TikTok",
                "statut": "ENABLE",
                "objective_type": "CONVERSIONS",
            },
        ]

    def _rows(self, *, impressions="100"):
        return [
            {
                "dimensions": {
                    "campaign_id": "555",
                    "stat_time_day": "2026-08-01 00:00:00",
                },
                "metrics": {
                    "impressions": impressions,
                    "clicks": "9",
                    "conversion": "3",
                    "spend": "15.67",
                },
            },
        ]

    @patch("predictor.tiktok_ads_sync.lister_performances_campagnes_tiktok")
    @patch("predictor.tiktok_ads_sync.lister_campagnes_tiktok")
    def test_sync_creates_campaign_and_daily_measure(
        self,
        campaigns,
        analytics,
    ):
        campaigns.return_value = self._campaigns()
        analytics.return_value = self._rows()

        resultat = synchroniser_compte_tiktok_ads(self.compte)

        self.assertEqual(resultat["campagnes"], 1)
        self.assertEqual(resultat["mesures"], 1)

        campagne = CampagneExterne.objects.get(
            compte=self.compte,
            identifiant_externe="555",
        )
        self.assertEqual(campagne.plateforme, "tiktok_ads")
        self.assertEqual(campagne.source_donnees, "api_regie")
        self.assertEqual(campagne.devise, "EUR")
        self.assertEqual(campagne.impressions, 100)
        self.assertEqual(campagne.clics, 9)
        self.assertEqual(campagne.depense, Decimal("15.67"))

        mesure = MesureCampagneExterne.objects.get(
            campagne=campagne
        )
        self.assertEqual(mesure.site, self.site)
        self.assertEqual(mesure.conversions, Decimal("3.0000"))
        self.assertEqual(mesure.depense, Decimal("15.67"))

        journal = JournalSynchronisationConnecteur.objects.get(
            compte=self.compte
        )
        self.assertEqual(
            journal.details["source"],
            "tiktok_ads_api",
        )

    @patch("predictor.tiktok_ads_sync.lister_performances_campagnes_tiktok")
    @patch("predictor.tiktok_ads_sync.lister_campagnes_tiktok")
    def test_sync_is_idempotent_by_campaign_and_date(
        self,
        campaigns,
        analytics,
    ):
        campaigns.return_value = self._campaigns()
        analytics.return_value = self._rows(impressions="100")

        synchroniser_compte_tiktok_ads(self.compte)
        analytics.return_value = self._rows(impressions="120")
        synchroniser_compte_tiktok_ads(self.compte)

        campagne = CampagneExterne.objects.get(
            compte=self.compte,
            identifiant_externe="555",
        )
        self.assertEqual(
            MesureCampagneExterne.objects.filter(
                campagne=campagne
            ).count(),
            1,
        )
        self.assertEqual(campagne.impressions, 120)

    @patch(
        "predictor.views.synchroniser_compte_depuis_utm",
        return_value=0,
    )
    @patch(
        "predictor.views.synchroniser_compte_tiktok_ads",
        return_value={
            "campagnes": 1,
            "mesures": 1,
            "periode": "LAST_30_DAYS",
        },
    )
    def test_connector_view_uses_native_tiktok_sync(
        self,
        native_sync,
        utm_sync,
    ):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse(
                "synchroniser_compte_connecteur",
                args=[self.compte.id],
            )
        )

        self.assertRedirects(
            response,
            f"{reverse('module_connecteurs')}?site={self.site.id}",
        )
        self.assertEqual(native_sync.call_count, 1)
        self.assertEqual(utm_sync.call_count, 0)
