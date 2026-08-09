from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .attribution import appliquer_attribution_opportunite
from .models import (
    ClientProfessionnel,
    LeadCapture,
    OpportuniteCRM,
    SessionVisiteur,
    SiteClient,
    Vente,
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
class VentePhase4ATests(TestCase):

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="vente-owner",
            email="vente@example.com",
            password="MotDePasse-Solide-2026!",
        )
        self.pro = ClientProfessionnel.objects.create(
            utilisateur=self.user,
            nom_entreprise="Entreprise Vente",
            statut_abonnement="actif",
            email_verifie_le=timezone.now(),
        )
        self.a = SiteClient.objects.create(
            client=self.pro,
            nom_site="Site A",
            domaine="a.example",
            actif=True,
        )
        self.b = SiteClient.objects.create(
            client=self.pro,
            nom_site="Site B",
            domaine="b.example",
            actif=True,
        )
        self.client.force_login(self.user)

    def make_opp(self, site, suffix):
        session = SessionVisiteur.objects.create(
            site=site,
            session_id=f"s-{suffix}",
            source_visite="meta",
            utm_source="meta",
            utm_medium="paid_social",
            utm_campaign=f"camp-{suffix}",
            landing_page="/offre",
        )
        lead = LeadCapture.objects.create(
            site=site,
            session=session,
            email=f"{suffix}@example.com",
            consentement=True,
            statut_suivi="contacte",
        )
        opportunity = OpportuniteCRM.objects.create(
            site=site,
            lead=lead,
            titre=f"Opp {suffix}",
            montant_estime=Decimal("3000"),
        )
        appliquer_attribution_opportunite(opportunity)
        opportunity.refresh_from_db()
        return lead, opportunity

    def test_won_creates_real_sale(self):
        lead, opportunity = self.make_opp(self.a, "won")

        response = self.client.post(
            reverse(
                "modifier_opportunite",
                args=[opportunity.id],
            ),
            {
                "site": str(self.a.id),
                "montant_estime": "3000",
                "montant_realise": "2490",
                "devise": "eur",
                "date_vente": "2026-08-09",
                "reference_vente": "CMD-1",
                "probabilite": "100",
                "etape": "gagne",
                "notes": "ok",
            },
        )

        self.assertEqual(response.status_code, 302)
        sale = Vente.objects.get(opportunite=opportunity)
        lead.refresh_from_db()

        self.assertEqual(sale.montant, Decimal("2490"))
        self.assertEqual(sale.devise, "EUR")
        self.assertEqual(
            sale.utm_campaign_attribution,
            "camp-won",
        )
        self.assertEqual(
            lead.statut_suivi,
            "converti",
        )

    def test_won_without_real_amount_invents_no_revenue(self):
        _, opportunity = self.make_opp(self.a, "noamount")

        self.client.post(
            reverse(
                "modifier_opportunite",
                args=[opportunity.id],
            ),
            {
                "site": str(self.a.id),
                "montant_estime": "9999",
                "montant_realise": "",
                "devise": "EUR",
                "date_vente": "",
                "reference_vente": "",
                "probabilite": "100",
                "etape": "gagne",
                "notes": "",
            },
        )

        self.assertFalse(
            Vente.objects.filter(
                opportunite=opportunity,
            ).exists()
        )

    def test_sale_amount_over_field_capacity_is_rejected(self):
        _, opportunity = self.make_opp(self.a, "too-large")

        with self.assertRaises(ValueError):
            enregistrer_vente_opportunite(
                opportunity,
                montant=Decimal("10000000000.00"),
                devise="EUR",
                reference_vente="TOO-LARGE",
            )

        self.assertFalse(
            Vente.objects.filter(
                opportunite=opportunity,
            ).exists()
        )

    def test_lost_cancels_sale(self):
        lead, opportunity = self.make_opp(self.a, "lost")
        sale = enregistrer_vente_opportunite(
            opportunity,
            montant=Decimal("1200"),
            reference_vente="CMD-LOST",
        )

        self.client.post(
            reverse(
                "modifier_opportunite",
                args=[opportunity.id],
            ),
            {
                "site": str(self.a.id),
                "montant_estime": "1200",
                "montant_realise": "1200",
                "devise": "EUR",
                "date_vente": "2026-08-09",
                "reference_vente": "CMD-LOST",
                "probabilite": "0",
                "etape": "perdu",
                "notes": "",
            },
        )

        sale.refresh_from_db()
        lead.refresh_from_db()

        self.assertEqual(sale.statut, "annulee")
        self.assertEqual(lead.statut_suivi, "perdu")

    def test_dashboard_revenue_is_site_isolated(self):
        _, opportunity_a = self.make_opp(self.a, "a")
        _, opportunity_b = self.make_opp(self.b, "b")

        enregistrer_vente_opportunite(
            opportunity_a,
            montant=Decimal("1500"),
            reference_vente="A-1",
        )
        enregistrer_vente_opportunite(
            opportunity_b,
            montant=Decimal("9000"),
            reference_vente="B-1",
        )

        response = self.client.get(
            reverse("dashboard"),
            {"site": str(self.a.id)},
        )

        self.assertEqual(
            response.context["total_ventes"],
            1,
        )
        self.assertEqual(
            response.context["chiffre_affaires_realise"],
            Decimal("1500"),
        )
        self.assertEqual(
            response.context["chiffre_affaires_attribue"],
            Decimal("1500"),
        )

    def test_cannot_modify_other_site_opportunity(self):
        _, opportunity = self.make_opp(self.b, "cross")

        self.client.post(
            reverse(
                "modifier_opportunite",
                args=[opportunity.id],
            ),
            {
                "site": str(self.a.id),
                "montant_estime": "1",
                "montant_realise": "1",
                "devise": "EUR",
                "probabilite": "100",
                "etape": "gagne",
                "notes": "cross",
            },
        )

        opportunity.refresh_from_db()

        self.assertNotEqual(
            opportunity.etape,
            "gagne",
        )
        self.assertFalse(
            Vente.objects.filter(
                opportunite=opportunity,
            ).exists()
        )

    def test_reference_may_repeat_on_different_sites(self):
        _, opportunity_a = self.make_opp(self.a, "refa")
        _, opportunity_b = self.make_opp(self.b, "refb")

        enregistrer_vente_opportunite(
            opportunity_a,
            montant=Decimal("100"),
            reference_vente="ORDER-42",
        )
        sale_b = enregistrer_vente_opportunite(
            opportunity_b,
            montant=Decimal("200"),
            reference_vente="ORDER-42",
        )

        self.assertEqual(sale_b.site, self.b)
