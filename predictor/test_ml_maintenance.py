
from datetime import timedelta
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from .analyse import analyser_session_automatique
from .ml import predire_probabilite
from .ml_training import _dataset_for_site, compter_resultats_resolus, entrainer_site
from .models import (
    ClientProfessionnel,
    EvenementUtilisateur,
    JournalMaintenance,
    LeadCapture,
    ModeleMachineLearning,
    PredictionBesoin,
    OpportuniteCRM,
    SessionVisiteur,
    SiteClient,
)


TEST_STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    STORAGES=TEST_STORAGES,
    PREDICTNEED_SITE_URL="https://predictneed-ia.com",
    PREDICTNEED_ML_MIN_SAMPLES=40,
    PREDICTNEED_ML_MIN_PER_CLASS=10,
    PREDICTNEED_ML_MIN_BALANCED_ACCURACY=0.55,
    PREDICTNEED_ANALYTICS_RETENTION_DAYS=395,
    PREDICTNEED_LEAD_RETENTION_DAYS=1095,
)
class MachineLearningMaintenanceTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="ml-owner",
            email="ml@example.com",
            password="MotDePasse-Solide-2026!",
        )
        self.client_pro = ClientProfessionnel.objects.create(
            utilisateur=self.user,
            nom_entreprise="Entreprise ML",
            statut_abonnement="actif",
        )
        self.site = SiteClient.objects.create(
            client=self.client_pro,
            nom_site="Site ML",
            domaine="ml.example",
            actif=True,
            module_prediction_avancee_actif=True,
        )
        self.other_site = SiteClient.objects.create(
            client=self.client_pro,
            nom_site="Autre site",
            domaine="other.example",
            actif=True,
            module_prediction_avancee_actif=True,
        )

    def _create_resolved_session(self, index, positive):
        session = SessionVisiteur.objects.create(
            site=self.site,
            session_id=f"resolved-{index}",
            nombre_pages_vues=5 if positive else 1,
            nombre_clics=4 if positive else 0,
            temps_total_secondes=180 if positive else 4,
            est_rebond=not positive,
            est_desktop=True,
        )
        if positive:
            EvenementUtilisateur.objects.create(
                session=session,
                type_evenement="page_vue",
                page="/prix/",
            )
            EvenementUtilisateur.objects.create(
                session=session,
                type_evenement="page_vue",
                page="/contact/",
            )
        else:
            EvenementUtilisateur.objects.create(
                session=session,
                type_evenement="page_vue",
                page="/blog/",
            )

        LeadCapture.objects.create(
            site=self.site,
            session=session,
            email=f"lead-{index}@example.com",
            consentement=True,
            statut_suivi="converti" if positive else "perdu",
        )
        return session

    def test_opportunity_outcomes_are_used_as_supervised_labels(self):
        positive_session = SessionVisiteur.objects.create(
            site=self.site,
            session_id="opportunity-won",
            nombre_pages_vues=4,
            nombre_clics=3,
            temps_total_secondes=120,
        )
        positive_lead = LeadCapture.objects.create(
            site=self.site,
            session=positive_session,
            email="won@example.com",
            consentement=True,
            statut_suivi="contacte",
        )
        OpportuniteCRM.objects.create(
            site=self.site,
            lead=positive_lead,
            titre="Vente gagnée",
            etape="gagne",
        )

        negative_session = SessionVisiteur.objects.create(
            site=self.site,
            session_id="opportunity-lost",
            nombre_pages_vues=2,
            nombre_clics=1,
            temps_total_secondes=30,
        )
        negative_lead = LeadCapture.objects.create(
            site=self.site,
            session=negative_session,
            email="lost@example.com",
            consentement=True,
            statut_suivi="contacte",
        )
        OpportuniteCRM.objects.create(
            site=self.site,
            lead=negative_lead,
            titre="Vente perdue",
            etape="perdu",
        )

        matrix, labels, session_ids = _dataset_for_site(self.site)

        self.assertEqual(len(matrix), 2)
        labels_by_session = dict(zip(session_ids, labels))
        self.assertEqual(labels_by_session[positive_session.pk], 1)
        self.assertEqual(labels_by_session[negative_session.pk], 0)

        counts = compter_resultats_resolus(self.site)
        self.assertEqual(counts["total"], 2)
        self.assertEqual(counts["positives"], 1)
        self.assertEqual(counts["negatives"], 1)

    def test_opportunity_outcome_takes_priority_over_lead_status(self):
        session = SessionVisiteur.objects.create(
            site=self.site,
            session_id="opportunity-priority",
        )
        lead = LeadCapture.objects.create(
            site=self.site,
            session=session,
            email="priority@example.com",
            consentement=True,
            statut_suivi="converti",
        )
        OpportuniteCRM.objects.create(
            site=self.site,
            lead=lead,
            titre="Finalement perdue",
            etape="perdu",
        )

        _, labels, session_ids = _dataset_for_site(self.site)
        labels_by_session = dict(zip(session_ids, labels))
        self.assertEqual(labels_by_session[session.pk], 0)

    def test_rules_are_used_without_active_model(self):
        session = SessionVisiteur.objects.create(
            site=self.site,
            session_id="rules-only",
        )
        result = analyser_session_automatique(session)
        self.assertEqual(result["moteur"], "regles")
        self.assertIsNone(result["probabilite_conversion"])

    def test_insufficient_data_does_not_create_model(self):
        result = entrainer_site(
            self.site,
            minimum_samples=40,
            minimum_per_class=10,
            minimum_balanced_accuracy=0.55,
        )
        self.assertEqual(result.status, "insufficient_data")
        self.assertFalse(
            ModeleMachineLearning.objects.filter(site=self.site).exists()
        )

    def test_training_activates_separate_site_model(self):
        for index in range(20):
            self._create_resolved_session(index, positive=True)
        for index in range(20, 40):
            self._create_resolved_session(index, positive=False)

        result = entrainer_site(
            self.site,
            minimum_samples=40,
            minimum_per_class=10,
            minimum_balanced_accuracy=0.55,
        )
        self.assertEqual(result.status, "trained")
        self.assertTrue(result.active)

        positive_probe = SessionVisiteur.objects.create(
            site=self.site,
            session_id="positive-probe",
            nombre_pages_vues=6,
            nombre_clics=5,
            temps_total_secondes=240,
            est_rebond=False,
        )
        EvenementUtilisateur.objects.create(
            session=positive_probe,
            type_evenement="page_vue",
            page="/prix/",
        )
        EvenementUtilisateur.objects.create(
            session=positive_probe,
            type_evenement="page_vue",
            page="/contact/",
        )

        prediction = predire_probabilite(positive_probe)
        self.assertIsNotNone(prediction)
        self.assertGreater(prediction["probabilite"], 0.5)

        automatic = analyser_session_automatique(positive_probe)
        self.assertEqual(automatic["moteur"], "machine_learning")
        self.assertTrue(automatic["version_modele"])

        other_probe = SessionVisiteur.objects.create(
            site=self.other_site,
            session_id="other-probe",
            nombre_pages_vues=6,
            nombre_clics=5,
            temps_total_secondes=240,
        )
        self.assertIsNone(predire_probabilite(other_probe))

    def test_daily_maintenance_purges_old_analytics_and_logs(self):
        old_session = SessionVisiteur.objects.create(
            site=self.site,
            session_id="old-session",
        )
        old_event = EvenementUtilisateur.objects.create(
            session=old_session,
            type_evenement="page_vue",
            page="/ancienne/",
        )
        old_prediction = PredictionBesoin.objects.create(
            session=old_session,
            profil="Ancien",
            besoin_probable="Ancien",
            intention="Faible",
            score=1,
            recommandation="Ancienne donnée",
        )
        cutoff = timezone.now() - timedelta(days=400)
        SessionVisiteur.objects.filter(pk=old_session.pk).update(
            derniere_activite=cutoff
        )
        EvenementUtilisateur.objects.filter(pk=old_event.pk).update(
            date_creation=cutoff
        )
        PredictionBesoin.objects.filter(pk=old_prediction.pk).update(
            date_creation=cutoff
        )

        output = StringIO()
        call_command("maintenance_quotidienne", stdout=output)

        self.assertFalse(
            SessionVisiteur.objects.filter(pk=old_session.pk).exists()
        )
        journal = JournalMaintenance.objects.filter(
            type_operation="maintenance_quotidienne"
        ).latest("date_debut")
        self.assertEqual(journal.statut, "succes")
        self.assertIn("purge_rgpd", journal.details)
