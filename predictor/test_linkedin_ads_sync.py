from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .external_connectors import signer_token
from .linkedin_ads_sync import synchroniser_compte_linkedin_ads
from .models import (
    CampagneExterne,
    ClientProfessionnel,
    CompteConnecteExterne,
    JournalSynchronisationConnecteur,
    MesureCampagneExterne,
    SiteClient,
)


FAKE_CONNECTORS = {
    "linkedin_ads": {
        "nom": "LinkedIn Ads",
        "description": "Test LinkedIn Ads",
        "client_id": "linkedin-client",
        "client_secret": "linkedin-secret",
        "api_version": "202606",
        "auth_url": "https://www.linkedin.com/oauth/v2/authorization",
        "token_url": "https://www.linkedin.com/oauth/v2/accessToken",
        "scopes": ["r_ads", "r_ads_reporting"],
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
class LinkedInAdsSyncTests(TestCase):

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="linkedin-sync",
            email="linkedin-sync@example.com",
            password="MotDePasse-Solide-2026!",
        )
        self.client_pro = ClientProfessionnel.objects.create(
            utilisateur=self.user,
            nom_entreprise="LinkedIn Sync",
            statut_abonnement="actif",
        )
        self.site = SiteClient.objects.create(
            client=self.client_pro,
            nom_site="LinkedIn Sync Site",
            domaine="linkedin-sync.example",
            actif=True,
            module_connecteurs_actif=True,
        )
        self.compte = CompteConnecteExterne.objects.create(
            client=self.client_pro,
            site=self.site,
            plateforme="linkedin_ads",
            identifiant_externe="123",
            nom_compte="Compte LinkedIn",
            statut="connecte",
            access_token_signe=signer_token("access-linkedin"),
            refresh_token_signe=signer_token("refresh-linkedin"),
            expires_at=timezone.now() + timedelta(hours=1),
            configuration={
                "source": "oauth_linkedin_ads",
                "account_id": "123",
                "devise": "USD",
            },
        )

    def _campaigns(self):
        return [
            {
                "campaign_id": "555",
                "urn": "urn:li:sponsoredCampaign:555",
                "nom": "Campagne LinkedIn",
                "statut": "ACTIVE",
            },
        ]

    def _rows(self, *, impressions="100"):
        return [
            {
                "pivotValues": ["urn:li:sponsoredCampaign:555"],
                "dateRange": {
                    "start": {
                        "year": 2026,
                        "month": 8,
                        "day": 1,
                    },
                    "end": {
                        "year": 2026,
                        "month": 8,
                        "day": 1,
                    },
                },
                "impressions": impressions,
                "landingPageClicks": "7",
                "externalWebsiteConversions": "2.5",
                "costInLocalCurrency": {
                    "amount": "12.34",
                    "currencyCode": "USD",
                },
            },
        ]

    @patch("predictor.linkedin_ads_sync.lister_performances_campagnes_linkedin")
    @patch("predictor.linkedin_ads_sync.lister_campagnes_linkedin")
    def test_sync_creates_campaign_and_daily_measure(
        self,
        campaigns,
        analytics,
    ):
        campaigns.return_value = self._campaigns()
        analytics.return_value = self._rows()

        resultat = synchroniser_compte_linkedin_ads(self.compte)

        self.assertEqual(resultat["campagnes"], 1)
        self.assertEqual(resultat["mesures"], 1)

        campagne = CampagneExterne.objects.get(
            compte=self.compte,
            identifiant_externe="555",
        )
        self.assertEqual(campagne.plateforme, "linkedin_ads")
        self.assertEqual(campagne.source_donnees, "api_regie")
        self.assertEqual(campagne.devise, "USD")
        self.assertEqual(campagne.impressions, 100)
        self.assertEqual(campagne.clics, 7)
        self.assertEqual(campagne.depense, Decimal("12.34"))

        mesure = MesureCampagneExterne.objects.get(
            campagne=campagne
        )
        self.assertEqual(mesure.site, self.site)
        self.assertEqual(mesure.conversions, Decimal("2.5000"))
        self.assertEqual(mesure.depense, Decimal("12.34"))

        journal = JournalSynchronisationConnecteur.objects.get(
            compte=self.compte
        )
        self.assertEqual(
            journal.details["source"],
            "linkedin_ads_api",
        )

    @patch("predictor.linkedin_ads_sync.lister_performances_campagnes_linkedin")
    @patch("predictor.linkedin_ads_sync.lister_campagnes_linkedin")
    def test_sync_is_idempotent_by_campaign_and_date(
        self,
        campaigns,
        analytics,
    ):
        campaigns.return_value = self._campaigns()
        analytics.return_value = self._rows(impressions="100")

        synchroniser_compte_linkedin_ads(self.compte)
        analytics.return_value = self._rows(impressions="120")
        synchroniser_compte_linkedin_ads(self.compte)

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
        "predictor.views.synchroniser_compte_linkedin_ads",
        return_value={
            "campagnes": 1,
            "mesures": 1,
            "periode": "LAST_30_DAYS",
        },
    )
    def test_connector_view_uses_native_linkedin_sync(
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
