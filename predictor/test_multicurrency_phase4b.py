from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from .ad_metrics import enregistrer_mesure_campagne_native
from .models import (
    CampagneExterne,
    ClientProfessionnel,
    CompteConnecteExterne,
    OpportuniteCRM,
    SiteClient,
)
from .sales import enregistrer_vente_opportunite


TEST_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


@override_settings(STORAGES=TEST_STORAGES)
class MultiCurrencySafetyTests(TestCase):

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="currency-owner",
            email="currency@example.com",
            password="MotDePasse-Solide-2026!",
        )
        self.pro = ClientProfessionnel.objects.create(
            utilisateur=self.user,
            nom_entreprise="Currency Corp",
            statut_abonnement="actif",
        )
        self.site = SiteClient.objects.create(
            client=self.pro,
            nom_site="Currency Site",
            domaine="currency.example",
            actif=True,
            module_connecteurs_actif=True,
        )
        self.client.force_login(self.user)

    def _opportunity(self, suffix):
        return OpportuniteCRM.objects.create(
            site=self.site,
            titre=f"Opp {suffix}",
            montant_estime=Decimal("100"),
        )

    def test_invalid_sale_currency_is_rejected(self):
        opportunity = self._opportunity("invalid")
        with self.assertRaises(ValueError):
            enregistrer_vente_opportunite(
                opportunity,
                montant=Decimal("100"),
                devise="EU",
            )

    def test_valid_foreign_currency_is_preserved(self):
        opportunity = self._opportunity("usd")
        sale = enregistrer_vente_opportunite(
            opportunity,
            montant=Decimal("125.50"),
            devise="usd",
        )
        self.assertEqual(sale.devise, "USD")

    def test_dashboard_does_not_sum_different_currencies(self):
        eur = self._opportunity("eur")
        usd = self._opportunity("usd-dashboard")
        enregistrer_vente_opportunite(eur, montant=Decimal("100"), devise="EUR")
        enregistrer_vente_opportunite(usd, montant=Decimal("250"), devise="USD")
        response = self.client.get(reverse("dashboard"), {"site": str(self.site.id)})
        self.assertIsNone(response.context["chiffre_affaires_realise"])
        self.assertEqual(
            response.context["chiffre_affaires_realise_par_devise"],
            [
                {"devise": "EUR", "total": Decimal("100")},
                {"devise": "USD", "total": Decimal("250")},
            ],
        )

    def test_single_currency_keeps_legacy_total_context(self):
        opportunity = self._opportunity("single")
        enregistrer_vente_opportunite(
            opportunity,
            montant=Decimal("300"),
            devise="EUR",
        )
        response = self.client.get(reverse("dashboard"), {"site": str(self.site.id)})
        self.assertEqual(response.context["chiffre_affaires_realise"], Decimal("300"))

    def test_campaign_rejects_second_currency(self):
        account = CompteConnecteExterne.objects.create(
            client=self.pro,
            site=self.site,
            plateforme="google_ads",
            nom_compte="Google Ads Currency",
            identifiant_externe="1234567890",
            statut="connecte",
        )
        campaign = CampagneExterne.objects.create(
            compte=account,
            site=self.site,
            plateforme="google_ads",
            source_donnees="api_regie",
            identifiant_externe="987654321",
            nom="Campaign Currency",
            devise="EUR",
        )
        enregistrer_mesure_campagne_native(
            campaign,
            date=date(2026, 8, 8),
            depense=Decimal("10"),
            devise="EUR",
        )
        with self.assertRaises(ValueError):
            enregistrer_mesure_campagne_native(
                campaign,
                date=date(2026, 8, 9),
                depense=Decimal("20"),
                devise="USD",
            )
