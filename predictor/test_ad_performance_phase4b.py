from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from .ad_metrics import enregistrer_mesure_campagne_native
from .ad_performance import calculer_performance_campagne
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


class CampaignFinancialPerformanceTests(TestCase):

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="performance-owner",
            email="performance@example.com",
            password="MotDePasse-Solide-2026!",
        )
        self.pro = ClientProfessionnel.objects.create(
            utilisateur=self.user,
            nom_entreprise="Performance Corp",
            statut_abonnement="actif",
        )
        self.site = SiteClient.objects.create(
            client=self.pro,
            nom_site="Performance Site",
            domaine="performance.example",
            actif=True,
            module_publicite_actif=True,
            module_connecteurs_actif=True,
        )
        self.account = CompteConnecteExterne.objects.create(
            client=self.pro,
            site=self.site,
            plateforme="google_ads",
            nom_compte="Google Ads Performance",
            identifiant_externe="1234567890",
            statut="connecte",
        )

    def make_campaign(
        self,
        external_id="111",
        *,
        currency="EUR",
        utm_campaign="",
        utm_source="",
        utm_medium="",
    ):
        return CampagneExterne.objects.create(
            compte=self.account,
            site=self.site,
            plateforme="google_ads",
            source_donnees="api_regie",
            identifiant_externe=external_id,
            nom=f"Campaign {external_id}",
            devise=currency,
            utm_campaign=utm_campaign,
            utm_source=utm_source,
            utm_medium=utm_medium,
        )

    def add_measure(
        self,
        campaign,
        day,
        *,
        spend,
        impressions=100,
        clicks=10,
        conversions="1.5",
        currency="EUR",
    ):
        enregistrer_mesure_campagne_native(
            campaign,
            date=day,
            impressions=impressions,
            clics=clicks,
            conversions=Decimal(conversions),
            depense=Decimal(spend),
            devise=currency,
        )

    def add_sale(
        self,
        *,
        amount,
        currency="EUR",
        utm_campaign="",
        utm_source="",
        utm_medium="",
        utm_id="",
        day=date(2026, 8, 9),
        suffix="sale",
    ):
        session = SessionVisiteur.objects.create(
            site=self.site,
            session_id=f"session-{suffix}",
            utm_campaign=utm_campaign,
            utm_source=utm_source,
            utm_medium=utm_medium,
            utm_id=utm_id,
        )
        lead = LeadCapture.objects.create(
            site=self.site,
            session=session,
            email=f"{suffix}@example.com",
            consentement=True,
            statut_suivi="contacte",
        )
        opportunity = OpportuniteCRM.objects.create(
            site=self.site,
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

    def test_native_campaign_with_utm_id_calculates_roas_and_roi(self):
        campaign = self.make_campaign("111")
        self.add_measure(
            campaign,
            date(2026, 8, 9),
            spend="100",
        )
        self.add_sale(
            amount="300",
            utm_id="111",
            suffix="native",
        )

        result = calculer_performance_campagne(campaign)

        self.assertEqual(
            result["chiffre_affaires_attribue"],
            Decimal("300.00"),
        )
        self.assertEqual(result["depense"], Decimal("100.00"))
        self.assertEqual(result["roas"], Decimal("3.00"))
        self.assertEqual(
            result["roi_publicitaire"],
            Decimal("200.0"),
        )
        self.assertEqual(
            result["statut_calcul"],
            "calculable",
        )

    def test_native_campaign_without_attribution_evidence_is_not_interpreted(self):
        campaign = self.make_campaign("222")
        self.add_measure(
            campaign,
            date(2026, 8, 9),
            spend="100",
        )

        result = calculer_performance_campagne(campaign)

        self.assertFalse(result["attribution_observable"])
        self.assertIsNone(result["roas"])
        self.assertIsNone(result["roi_publicitaire"])
        self.assertEqual(
            result["statut_calcul"],
            "attribution_insuffisante",
        )

    def test_observable_campaign_with_no_sale_returns_zero_roas(self):
        campaign = self.make_campaign("333")
        self.add_measure(
            campaign,
            date(2026, 8, 9),
            spend="80",
        )
        SessionVisiteur.objects.create(
            site=self.site,
            session_id="session-observable",
            utm_id="333",
        )

        result = calculer_performance_campagne(campaign)

        self.assertEqual(result["roas"], Decimal("0.00"))
        self.assertEqual(
            result["roi_publicitaire"],
            Decimal("-100.0"),
        )

    def test_mixed_currency_sale_blocks_financial_ratio(self):
        campaign = self.make_campaign("444")
        self.add_measure(
            campaign,
            date(2026, 8, 9),
            spend="100",
        )
        self.add_sale(
            amount="200",
            currency="USD",
            utm_id="444",
            suffix="usd",
        )

        result = calculer_performance_campagne(campaign)

        self.assertEqual(
            result["statut_calcul"],
            "devise_incompatible",
        )
        self.assertIsNone(result["roas"])
        self.assertEqual(
            result["ventes_devise_incompatible"],
            1,
        )

    def test_utm_campaign_requires_source_and_medium_when_present(self):
        campaign = self.make_campaign(
            "utm-row",
            utm_campaign="summer",
            utm_source="google",
            utm_medium="cpc",
        )
        self.add_measure(
            campaign,
            date(2026, 8, 9),
            spend="50",
        )
        self.add_sale(
            amount="120",
            utm_campaign="summer",
            utm_source="meta",
            utm_medium="cpc",
            suffix="wrong-source",
        )

        result = calculer_performance_campagne(campaign)

        self.assertEqual(result["ventes_attribuees"], 0)
        self.assertEqual(result["roas"], Decimal("0.00"))

    def test_date_range_scopes_spend_and_sales(self):
        campaign = self.make_campaign("555")
        self.add_measure(
            campaign,
            date(2026, 8, 1),
            spend="40",
        )
        self.add_measure(
            campaign,
            date(2026, 8, 9),
            spend="100",
        )
        self.add_sale(
            amount="200",
            utm_id="555",
            day=date(2026, 8, 1),
            suffix="old",
        )
        self.add_sale(
            amount="300",
            utm_id="555",
            day=date(2026, 8, 9),
            suffix="current",
        )

        result = calculer_performance_campagne(
            campaign,
            date_debut=date(2026, 8, 8),
            date_fin=date(2026, 8, 10),
        )

        self.assertEqual(result["depense"], Decimal("100.00"))
        self.assertEqual(
            result["chiffre_affaires_attribue"],
            Decimal("300.00"),
        )
        self.assertEqual(result["ventes_attribuees"], 1)

    def test_cancelled_sale_is_excluded(self):
        campaign = self.make_campaign("666")
        self.add_measure(
            campaign,
            date(2026, 8, 9),
            spend="100",
        )
        sale = self.add_sale(
            amount="500",
            utm_id="666",
            suffix="cancelled",
        )
        sale.statut = "annulee"
        sale.save(
            update_fields=[
                "statut",
                "date_mise_a_jour",
            ]
        )
        SessionVisiteur.objects.create(
            site=self.site,
            session_id="session-666-visible",
            utm_id="666",
        )

        result = calculer_performance_campagne(campaign)

        self.assertEqual(
            result["chiffre_affaires_attribue"],
            Decimal("0.00"),
        )
        self.assertEqual(result["roas"], Decimal("0.00"))

    def test_refunded_sale_is_excluded_from_ad_revenue(self):
        campaign = self.make_campaign("667")
        self.add_measure(
            campaign,
            date(2026, 8, 9),
            spend="100",
        )
        sale = self.add_sale(
            amount="500",
            utm_id="667",
            suffix="refunded",
        )
        sale.statut = "remboursee"
        sale.save(
            update_fields=[
                "statut",
                "date_mise_a_jour",
            ]
        )
        SessionVisiteur.objects.create(
            site=self.site,
            session_id="session-667-visible",
            utm_id="667",
        )

        result = calculer_performance_campagne(campaign)

        self.assertEqual(
            result["chiffre_affaires_attribue"],
            Decimal("0.00"),
        )
        self.assertEqual(result["ventes_attribuees"], 0)
        self.assertEqual(result["roas"], Decimal("0.00"))

    def test_missing_spend_never_invents_roi(self):
        campaign = self.make_campaign(
            "777",
            utm_campaign="tracked",
        )
        self.add_sale(
            amount="300",
            utm_campaign="tracked",
            suffix="no-spend",
        )

        result = calculer_performance_campagne(campaign)

        self.assertEqual(
            result["statut_calcul"],
            "depense_indisponible",
        )
        self.assertIsNone(result["roas"])
        self.assertIsNone(result["roi_publicitaire"])
