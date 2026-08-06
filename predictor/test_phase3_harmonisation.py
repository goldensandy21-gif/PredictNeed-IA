from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import ClientProfessionnel, SiteClient

TEST_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    STORAGES=TEST_STORAGES,
    PREDICTNEED_SITE_URL="https://predictneed-ia.com",
    PREDICTNEED_SUBSCRIPTION_TRIAL_DAYS=60,
    PREDICTNEED_ML_MIN_SAMPLES=40,
    PREDICTNEED_ML_MIN_PER_CLASS=10,
)
class Phase3HarmonisationTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="phase3-user", email="phase3@example.com", password="MotDePasse-Solide-2026!")
        self.client_pro = ClientProfessionnel.objects.create(utilisateur=self.user, nom_entreprise="Phase 3", statut_abonnement="actif")
        self.site_prediction = SiteClient.objects.create(client=self.client_pro, nom_site="Site prédiction", domaine="prediction.example", module_prediction_avancee_actif=True, module_ecommerce_actif=False)
        self.site_ecommerce = SiteClient.objects.create(client=self.client_pro, nom_site="Site e-commerce", domaine="ecommerce.example", module_prediction_avancee_actif=False, module_ecommerce_actif=True)

    def test_dashboard_modules_follow_selected_site(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("dashboard"), {"site": self.site_prediction.pk})
        self.assertTrue(response.context["a_module_prediction_avancee"])
        self.assertFalse(response.context["a_module_ecommerce"])
        response = self.client.get(reverse("dashboard"), {"site": self.site_ecommerce.pk})
        self.assertFalse(response.context["a_module_prediction_avancee"])
        self.assertTrue(response.context["a_module_ecommerce"])

    def test_dashboard_has_no_fake_ecommerce_numbers(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("dashboard"), {"site": self.site_ecommerce.pk})
        self.assertContains(response, "Aucun chiffre fictif n’est affiché")
        self.assertContains(response, "Consulter les statistiques e-commerce")

    def test_guide_documents_security_ml_and_retention(self):
        response = self.client.get(reverse("guide_utilisation"))
        for value in ["40 sessions résolues", "10 conversions", "10 pertes", "395 jours", "1 095 jours", "Mot de passe oublié", "Machine learning supervisé"]:
            self.assertContains(response, value)

    def test_public_pages_available(self):
        routes = ["accueil", "fonctionnalites", "prix", "simulateur", "guide_utilisation", "mentions_legales", "politique_confidentialite", "conditions_generales_utilisation", "politique_cookies", "accord_traitement_donnees", "a_propos", "contact", "connexion", "inscription", "password_reset"]
        for route in routes:
            with self.subTest(route=route):
                self.assertEqual(self.client.get(reverse(route)).status_code, 200)

    def test_legal_stale_fragments_removed(self):
        mentions = self.client.get(reverse("mentions_legales"))
        self.assertNotContains(mentions, "devra être ajoutée ici")
        self.assertNotContains(mentions, "Charte du respect de la vie privée")
        cookies = self.client.get(reverse("politique_cookies"))
        self.assertNotContains(cookies, "predictneed_popup_shown")
        self.assertContains(cookies, "predictneed_consent_v3")
        self.assertContains(cookies, "predictneed_session_id")
        self.assertContains(cookies, "predictneed_lead_sent")

    def test_simulator_is_rule_based(self):
        response = self.client.get(reverse("simulateur"))
        self.assertContains(response, "n’entraîne et n’utilise aucun modèle de machine learning")
