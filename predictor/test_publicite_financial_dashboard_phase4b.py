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
    LeadCapture,
    OpportuniteCRM,
    SessionVisiteur,
    SiteClient,
)
from .sales import enregistrer_vente_opportunite


TEST_STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}


@override_settings(STORAGES=TEST_STORAGES)
class PubliciteFinancialDashboardTests(TestCase):

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="publicite-finance-owner",
            email="publicite-finance@example.com",
            password="MotDePasse-Solide-2026!",
        )
        self.pro = ClientProfessionnel.objects.create(
            utilisateur=self.user,
            nom_entreprise="Publicite Finance Corp",
            statut_abonnement="actif",
        )
        self.site_a = SiteClient.objects.create(
            client=self.pro,
            nom_site="Publicite Site A",
            domaine="publicite-a.example",
            actif=True,
            module_publicite_actif=True,
            module_connecteurs_actif=True,
        )
        self.site_b = SiteClient.objects.create(
            client=self.pro,
            nom_site="Publicite Site B",
            domaine="publicite-b.example",
            actif=True,
            module_publicite_actif=True,
            module_connecteurs_actif=True,
        )
        self.account_a = CompteConnecteExterne.objects.create(
            client=self.pro,
            site=self.site_a,
            plateforme="google_ads",
            nom_compte="Google Ads A",
            identifiant_externe="1234567890",
            statut="connecte",
        )
        self.account_b = CompteConnecteExterne.objects.create(
            client=self.pro,
            site=self.site_b,
            plateforme="google_ads",
            nom_compte="Google Ads B",
            identifiant_externe="2234567890",
            statut="connecte",
        )
        self.client.force_login(self.user)

    def make_campaign(
        self,
        external_id,
        *,
        site=None,
        account=None,
        currency="EUR",
    ):
        site = site or self.site_a
        account = account or self.account_a
        return CampagneExterne.objects.create(
            compte=account,
            site=site,
            plateforme="google_ads",
            source_donnees="api_regie",
            identifiant_externe=external_id,
            nom=f"Campaign {external_id}",
            devise=currency,
        )

    def add_measure(
        self,
        campaign,
        day,
        spend,
        *,
        currency="EUR",
    ):
        enregistrer_mesure_campagne_native(
            campaign,
            date=day,
            impressions=1000,
            clics=100,
            conversions=Decimal("2.5"),
            depense=Decimal(spend),
            devise=currency,
        )

    def add_sale(
        self,
        campaign_id,
        amount,
        *,
        currency="EUR",
        day=date(2026, 8, 9),
        suffix="sale",
    ):
        session = SessionVisiteur.objects.create(
            site=self.site_a,
            session_id=f"publicite-{suffix}",
            utm_source="google",
            utm_medium="cpc",
            utm_id=campaign_id,
        )
        lead = LeadCapture.objects.create(
            site=self.site_a,
            session=session,
            email=f"{suffix}@example.com",
            consentement=True,
            statut_suivi="contacte",
        )
        opportunity = OpportuniteCRM.objects.create(
            site=self.site_a,
            lead=lead,
            titre=f"Opportunity {suffix}",
            montant_estime=Decimal(amount),
        )
        return enregistrer_vente_opportunite(
            opportunity,
            montant=Decimal(amount),
            devise=currency,
            date_vente=day,
            reference_vente=f"REF-{suffix}",
        )

    def get_publicite(self, **extra):
        params = {"site": str(self.site_a.id)}
        params.update(extra)
        return self.client.get(
            reverse("module_publicite"),
            params,
        )

    def test_module_exposes_roas_roi_and_recommendation(self):
        campaign = self.make_campaign("111")
        self.add_measure(
            campaign,
            date(2026, 8, 9),
            "100",
        )
        self.add_sale(
            "111",
            "300",
            suffix="roas",
        )

        response = self.get_publicite()

        self.assertEqual(response.status_code, 200)
        performance = response.context[
            "performances_campagnes"
        ][0]

        self.assertEqual(
            performance["depense"],
            Decimal("100.00"),
        )
        self.assertEqual(
            performance["chiffre_affaires_attribue"],
            Decimal("300.00"),
        )
        self.assertEqual(
            performance["roas"],
            Decimal("3.00"),
        )
        self.assertEqual(
            performance["roi_publicitaire"],
            Decimal("200.0"),
        )
        self.assertEqual(
            response.context[
                "campagnes_financieres_calculables"
            ],
            1,
        )
        self.assertContains(response, "ROAS")
        self.assertContains(
            response,
            "ROI publicitaire",
        )

    def test_date_filter_scopes_spend_and_revenue(self):
        campaign = self.make_campaign("222")
        self.add_measure(
            campaign,
            date(2026, 8, 1),
            "40",
        )
        self.add_measure(
            campaign,
            date(2026, 8, 9),
            "100",
        )
        self.add_sale(
            "222",
            "200",
            day=date(2026, 8, 1),
            suffix="old",
        )
        self.add_sale(
            "222",
            "300",
            day=date(2026, 8, 9),
            suffix="current",
        )

        response = self.get_publicite(
            date_debut="2026-08-08",
            date_fin="2026-08-10",
        )
        performance = response.context[
            "performances_campagnes"
        ][0]

        self.assertEqual(
            performance["depense"],
            Decimal("100.00"),
        )
        self.assertEqual(
            performance["chiffre_affaires_attribue"],
            Decimal("300.00"),
        )
        self.assertEqual(
            performance["ventes_attribuees"],
            1,
        )

    def test_campaign_from_other_site_is_not_exposed(self):
        self.make_campaign(
            "other-site",
            site=self.site_b,
            account=self.account_b,
        )

        response = self.get_publicite()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["performances_campagnes"],
            [],
        )

    def test_unobservable_campaign_shows_no_financial_ratio(self):
        campaign = self.make_campaign("333")
        self.add_measure(
            campaign,
            date(2026, 8, 9),
            "100",
        )

        response = self.get_publicite()
        performance = response.context[
            "performances_campagnes"
        ][0]

        self.assertEqual(
            performance["statut_calcul"],
            "attribution_insuffisante",
        )
        self.assertIsNone(performance["roas"])
        self.assertEqual(
            response.context[
                "campagnes_financieres_a_verifier"
            ],
            1,
        )
        self.assertContains(
            response,
            "Attribution insuffisante",
        )

    def test_incompatible_currency_is_visible_without_ratio(self):
        campaign = self.make_campaign("444")
        self.add_measure(
            campaign,
            date(2026, 8, 9),
            "100",
        )
        self.add_sale(
            "444",
            "250",
            currency="USD",
            suffix="usd",
        )

        response = self.get_publicite()
        performance = response.context[
            "performances_campagnes"
        ][0]

        self.assertEqual(
            performance["statut_calcul"],
            "devise_incompatible",
        )
        self.assertIsNone(performance["roas"])
        self.assertContains(
            response,
            "Devises incompatibles",
        )

    def test_missing_spend_never_displays_invented_ratio(self):
        self.make_campaign("555")
        self.add_sale(
            "555",
            "300",
            suffix="no-spend",
        )

        response = self.get_publicite()
        performance = response.context[
            "performances_campagnes"
        ][0]

        self.assertEqual(
            performance["statut_calcul"],
            "depense_indisponible",
        )
        self.assertIsNone(performance["roas"])
        self.assertIsNone(
            performance["roi_publicitaire"]
        )
