from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import (
    CampagneExterne,
    ClientProfessionnel,
    CompteConnecteExterne,
    LeadCapture,
    PredictionBesoin,
    SessionVisiteur,
    SiteClient,
)


@override_settings(
    STORAGES={
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }
)
class PublicitePlatformIsolationTests(TestCase):

    def setUp(self):
        User = get_user_model()

        self.user = User.objects.create_user(
            username="publicite-isolation",
            password="Test-2026-solide!",
        )

        self.client_pro = ClientProfessionnel.objects.create(
            utilisateur=self.user,
            nom_entreprise="Isolation Publicité",
            statut_abonnement="actif",
        )

        self.site = SiteClient.objects.create(
            client=self.client_pro,
            nom_site="Site Isolation",
            domaine="isolation.example",
            actif=True,
            module_publicite_actif=True,
        )

        self.sources = {
            "google_ads": "google",
            "meta_ads": "facebook",
            "tiktok_ads": "tiktok",
            "linkedin_ads": "linkedin",
        }

        self.comptes = {}

        for plateforme, source in self.sources.items():
            compte = CompteConnecteExterne.objects.create(
                client=self.client_pro,
                site=self.site,
                plateforme=plateforme,
                nom_compte=f"Compte {plateforme}",
                identifiant_externe=f"account-{plateforme}",
                statut="connecte",
            )

            self.comptes[plateforme] = compte

            CampagneExterne.objects.create(
                compte=compte,
                site=self.site,
                plateforme=plateforme,
                identifiant_externe=f"campaign-{plateforme}",
                nom=f"Campagne {plateforme}",
                utm_source=source,
                utm_campaign=f"campaign-{plateforme}",
            )

            session = SessionVisiteur.objects.create(
                site=self.site,
                session_id=f"session-{plateforme}",
                utm_source=source,
                utm_medium="paid",
                utm_campaign=f"campaign-{plateforme}",
            )

            LeadCapture.objects.create(
                site=self.site,
                session=session,
            )

            PredictionBesoin.objects.create(
                session=session,
                profil="Acheteur",
                besoin_probable="Offre",
                intention="Forte",
                score=10,
                recommandation="Contacter",
            )

        # Donnée volontairement incohérente :
        # plateforme Meta attachée à un compte Google.
        # Elle ne doit apparaître dans AUCUN des deux onglets.
        CampagneExterne.objects.create(
            compte=self.comptes["google_ads"],
            site=self.site,
            plateforme="meta_ads",
            identifiant_externe="campaign-mismatch",
            nom="Campagne incohérente",
        )

        self.client.force_login(self.user)

    def test_isolation_complete_des_quatre_regies(self):
        for plateforme in self.sources:
            with self.subTest(plateforme=plateforme):
                response = self.client.get(
                    reverse("module_publicite"),
                    {
                        "site": self.site.id,
                        "plateforme_pub": plateforme,
                        "date_debut": timezone.localdate().isoformat(),
                        "date_fin": timezone.localdate().isoformat(),
                    },
                )

                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    response.context["plateforme_pub"],
                    plateforme,
                )

                comptes = list(
                    response.context["comptes_externes"]
                )
                campagnes = response.context[
                    "campagnes_externes"
                ]
                performances = response.context[
                    "performances_campagnes"
                ]

                self.assertEqual(len(comptes), 1)
                self.assertEqual(
                    comptes[0].plateforme,
                    plateforme,
                )

                self.assertEqual(len(campagnes), 1)
                self.assertEqual(
                    campagnes[0].plateforme,
                    plateforme,
                )
                self.assertEqual(
                    campagnes[0].compte.plateforme,
                    plateforme,
                )

                self.assertEqual(len(performances), 1)
                self.assertEqual(
                    performances[0]["campagne"].plateforme,
                    plateforme,
                )

                self.assertEqual(
                    response.context["sessions_publicitaires"],
                    1,
                )
                self.assertEqual(
                    response.context["leads_publicitaires"],
                    1,
                )
                self.assertEqual(
                    response.context[
                        "intentions_fortes_publicitaires"
                    ],
                    1,
                )
