"""Tests de la démonstration commerciale du simulateur (/simulateur/).

Ces tests couvrent uniquement la nouvelle logique ajoutée pour transformer
/simulateur/ en démonstration commerciale : analyser_simulation_avancee()
(secteurs, signaux, score explicable) et le rendu de la vue simulateur().

Ils ne touchent ni analyser_besoin() (widget d'accueil) ni
analyser_session_automatique() (analyse réelle des sessions trackées) :
ces deux fonctions restent inchangées et ne sont pas re-testées ici.
"""
from django.test import TestCase
from django.urls import reverse

from predictor.analyse import (
    SECTEUR_PAR_DEFAUT,
    SECTEURS_SIMULATEUR,
    analyser_simulation_avancee,
)
from predictor.models import EvenementUtilisateur, PredictionBesoin, SessionVisiteur


# ---------------------------------------------------------------------------
# Scénarios rapides — doivent refléter exactement les presets JS de
# simulateur.html pour que les boutons "scénario rapide" restent cohérents
# avec la logique serveur.
# ---------------------------------------------------------------------------

SCENARIO_CURIEUX = {
    "pages": ["fonctionnalites"],
    "source": "organique",
    "premiere_visite": "oui",
    "nombre_visites": "1",
    "retour_page": None,
    "duree": "courte",
    "interactions": "faible",
    "cta_consulte": None,
    "abandon": None,
}

SCENARIO_COMPARATEUR = {
    "pages": ["fonctionnalites", "tarifs", "cas_clients"],
    "source": "organique",
    "premiere_visite": "oui",
    "nombre_visites": "2-3",
    "retour_page": "oui",
    "duree": "moyenne",
    "interactions": "moyen",
    "cta_consulte": None,
    "abandon": None,
}

SCENARIO_HESITANT = {
    "pages": ["tarifs"],
    "source": "organique",
    "premiere_visite": "non",
    "nombre_visites": "2-3",
    "retour_page": "oui",
    "duree": "moyenne",
    "interactions": "faible",
    "cta_consulte": "oui",
    "abandon": "oui",
}

SCENARIO_CHAUD = {
    "pages": ["fonctionnalites", "cas_clients", "tarifs", "essai"],
    "source": "organique",
    "premiere_visite": "non",
    "nombre_visites": "4+",
    "retour_page": "oui",
    "duree": "longue",
    "interactions": "eleve",
    "cta_consulte": "oui",
    "abandon": None,
}

SCENARIO_RECURRENT = {
    "pages": ["fonctionnalites", "cas_clients"],
    "source": "organique",
    "premiere_visite": "non",
    "nombre_visites": "2-3",
    "retour_page": "oui",
    "duree": "moyenne",
    "interactions": "moyen",
    "cta_consulte": None,
    "abandon": None,
}

SCENARIO_CAMPAGNE = {
    "pages": ["fonctionnalites"],
    "source": "payant",
    "premiere_visite": "oui",
    "nombre_visites": "1",
    "retour_page": None,
    "duree": "moyenne",
    "interactions": "moyen",
    "cta_consulte": None,
    "abandon": None,
}


class SecteursCatalogueTests(TestCase):
    def test_six_secteurs_attendus_sont_presents(self):
        self.assertEqual(
            set(SECTEURS_SIMULATEUR.keys()),
            {"saas", "formation", "agence", "conseil", "ecommerce", "immobilier"},
        )

    def test_chaque_secteur_a_cinq_pages_et_une_action(self):
        for cle, config in SECTEURS_SIMULATEUR.items():
            self.assertEqual(len(config["pages"]), 5, cle)
            self.assertTrue(config["action"], cle)
            self.assertIn(config["page_tarifs"], [p["value"] for p in config["pages"]], cle)
            self.assertIn(config["page_conversion"], [p["value"] for p in config["pages"]], cle)


class AnalyserSimulationAvanceeScenariosTests(TestCase):
    """Chaque scénario rapide doit produire le profil annoncé par son bouton,
    et les 6 scénarios pris ensemble doivent démontrer naturellement les 3
    niveaux d'intention (aucun ne doit dépendre d'un plafonnement caché)."""

    SCENARIOS_ET_NIVEAUX_ATTENDUS = [
        (SCENARIO_CURIEUX, "Visiteur curieux", "Faible", 0),
        (SCENARIO_COMPARATEUR, "Comparateur actif", "Moyenne", 45),
        (SCENARIO_HESITANT, "Visiteur hésitant", "Moyenne", 40),
        (SCENARIO_CHAUD, "Prospect chaud", "Élevée", 100),
        (SCENARIO_RECURRENT, "Visiteur récurrent", "Moyenne", 40),
        (SCENARIO_CAMPAGNE, "Prospect issu de campagne", "Faible", 10),
    ]

    def test_chaque_scenario_a_le_profil_le_niveau_et_le_score_attendus(self):
        for signaux, profil_attendu, niveau_attendu, score_attendu in self.SCENARIOS_ET_NIVEAUX_ATTENDUS:
            resultat = analyser_simulation_avancee("saas", signaux)
            self.assertEqual(resultat["profil"], profil_attendu, signaux)
            self.assertEqual(resultat["niveau"], niveau_attendu, signaux)
            self.assertEqual(resultat["score"], score_attendu, signaux)

    def test_les_6_scenarios_couvrent_les_3_niveaux_naturellement(self):
        """Ne doit jamais tous atterrir sur le même niveau (le vrai bug
        signalé était que tout semblait extrême à cause du plafonnage
        silencieux à 100)."""
        niveaux = {
            niveau_attendu
            for _, _, niveau_attendu, _ in self.SCENARIOS_ET_NIVEAUX_ATTENDUS
        }
        self.assertEqual(niveaux, {"Faible", "Moyenne", "Élevée"})

    def test_scenario_prospect_chaud_priorite_elevee(self):
        resultat = analyser_simulation_avancee("saas", SCENARIO_CHAUD)
        self.assertEqual(resultat["priorite_commerciale"], "Élevée")


class DecompositionCoherenteAvecLeScoreTests(TestCase):
    """Règle obligatoire : la somme des points affichés dans la
    décomposition doit toujours être strictement égale au score final
    affiché, y compris dans les cas limites où un plafond serait atteint."""

    def test_somme_de_la_decomposition_egale_le_score_pour_les_6_scenarios(self):
        for signaux in [
            SCENARIO_CURIEUX,
            SCENARIO_COMPARATEUR,
            SCENARIO_HESITANT,
            SCENARIO_CHAUD,
            SCENARIO_RECURRENT,
            SCENARIO_CAMPAGNE,
        ]:
            resultat = analyser_simulation_avancee("saas", signaux)
            somme = sum(item["points"] for item in resultat["decomposition"])
            self.assertEqual(somme, resultat["score"], signaux)

    def test_somme_egale_le_score_meme_avec_tous_les_signaux_positifs_actives(self):
        """Cas limite volontairement extrême : cocher toutes les pages et
        tous les signaux positifs à la fois ne doit jamais faire dépasser
        100 ni créer d'écart entre décomposition et score."""
        signaux_maximaux = {
            "pages": ["fonctionnalites", "cas_clients", "integrations", "tarifs", "essai"],
            "source": "payant",
            "premiere_visite": "non",
            "nombre_visites": "4+",
            "retour_page": "oui",
            "duree": "longue",
            "interactions": "eleve",
            "cta_consulte": "oui",
            "abandon": None,
        }
        resultat = analyser_simulation_avancee("saas", signaux_maximaux)
        somme = sum(item["points"] for item in resultat["decomposition"])
        self.assertEqual(somme, resultat["score"])
        self.assertEqual(resultat["score"], 100)

    def test_somme_egale_le_score_quand_abandon_seul_est_coche(self):
        """Cas limite où l'abandon (poids négatif) pourrait faire passer le
        score sous 0 : le delta réellement appliqué doit être réduit en
        conséquence, pas le score arbitrairement remonté à 0 sans ajuster
        la décomposition."""
        resultat = analyser_simulation_avancee("saas", {"abandon": "oui"})
        somme = sum(item["points"] for item in resultat["decomposition"])
        self.assertEqual(somme, resultat["score"])
        self.assertEqual(resultat["score"], 0)

    def test_aucune_composante_positive_ne_peut_a_elle_seule_depasser_100(self):
        """Filet de sécurité générique : quels que soient les signaux
        (y compris des combinaisons non couvertes par les 6 scénarios),
        l'invariant somme(décomposition) == score doit toujours tenir."""
        combinaisons = [
            {"pages": ["tarifs"], "duree": "longue"},
            {"pages": ["essai"], "interactions": "eleve", "cta_consulte": "oui"},
            {"nombre_visites": "4+", "premiere_visite": "non", "retour_page": "oui"},
            {"pages": ["tarifs", "essai", "cas_clients"], "cta_consulte": "oui", "abandon": "oui"},
        ]
        for signaux in combinaisons:
            resultat = analyser_simulation_avancee("saas", signaux)
            somme = sum(item["points"] for item in resultat["decomposition"])
            self.assertEqual(somme, resultat["score"], signaux)
            self.assertGreaterEqual(resultat["score"], 0)
            self.assertLessEqual(resultat["score"], 100)


class AnalyserSimulationAvanceeStructureTests(TestCase):
    def test_score_est_borne_entre_0_et_100(self):
        resultat = analyser_simulation_avancee("saas", SCENARIO_CHAUD)
        self.assertGreaterEqual(resultat["score"], 0)
        self.assertLessEqual(resultat["score"], 100)

        resultat_vide = analyser_simulation_avancee("saas", {})
        self.assertGreaterEqual(resultat_vide["score"], 0)

    def test_secteur_inconnu_retombe_sur_le_secteur_par_defaut(self):
        resultat = analyser_simulation_avancee("secteur-qui-nexiste-pas", SCENARIO_CURIEUX)
        self.assertEqual(
            resultat["secteur_label"],
            SECTEURS_SIMULATEUR[SECTEUR_PAR_DEFAUT]["label"],
        )

    def test_decomposition_et_signaux_explicatifs_sont_coherents(self):
        resultat = analyser_simulation_avancee("saas", SCENARIO_CHAUD)
        self.assertGreater(len(resultat["decomposition"]), 0)
        self.assertLessEqual(len(resultat["signaux_explicatifs"]), 5)
        labels_decomposition = {item["label"] for item in resultat["decomposition"]}
        for signal in resultat["signaux_explicatifs"]:
            self.assertIn(signal, labels_decomposition)

    def test_abandon_ajoute_un_point_negatif_explicite(self):
        resultat = analyser_simulation_avancee("saas", SCENARIO_HESITANT)
        points_abandon = [
            item["points"] for item in resultat["decomposition"]
            if item["label"] == "Abandon avant conversion"
        ]
        self.assertEqual(points_abandon, [-15])

    def test_besoin_et_recommandation_utilisent_action_du_secteur(self):
        resultat = analyser_simulation_avancee("formation", SCENARIO_HESITANT)
        self.assertIn("s'inscrire au programme", resultat["besoin_probable"])

    def test_analytics_classique_reflete_les_signaux_bruts(self):
        resultat = analyser_simulation_avancee("saas", SCENARIO_CHAUD)
        self.assertEqual(resultat["analytics_classique"]["pages_vues"], 4)
        self.assertEqual(resultat["analytics_classique"]["duree"], "Longue")

    def test_aucune_donnee_fictive_presentee_comme_reelle(self):
        """Aucun texte du résultat ne doit prétendre à une certitude absolue."""
        resultat = analyser_simulation_avancee("saas", SCENARIO_CHAUD)
        textes = " ".join([
            resultat["besoin_probable"],
            resultat["recommandation"],
            resultat["profil"],
        ]).lower()
        for expression_interdite in ["garanti", "certain à 100", "lit dans les pensées"]:
            self.assertNotIn(expression_interdite, textes)


class SimulateurVueTests(TestCase):
    def test_get_affiche_les_six_secteurs(self):
        response = self.client.get(reverse("simulateur"))
        self.assertEqual(response.status_code, 200)
        for config in SECTEURS_SIMULATEUR.values():
            self.assertContains(response, config["label"])

    def test_get_affiche_les_scenarios_rapides(self):
        response = self.client.get(reverse("simulateur"))
        for scenario in [
            "Visiteur curieux",
            "Comparateur actif",
            "Visiteur hésitant",
            "Prospect chaud",
            "Visiteur récurrent",
        ]:
            self.assertContains(response, scenario)

    def test_get_affiche_le_texte_de_transparence_obligatoire(self):
        response = self.client.get(reverse("simulateur"))
        self.assertContains(
            response,
            "Cette simulation illustre la logique de décision de PredictNeed IA",
        )

    def test_get_affiche_les_deux_cta(self):
        response = self.client.get(reverse("simulateur"))
        self.assertContains(response, "Créer mon espace PredictNeed IA")
        self.assertContains(response, "Découvrir toutes les fonctionnalités")
        self.assertContains(response, reverse("inscription"))
        self.assertContains(response, reverse("fonctionnalites"))

    def test_post_affiche_le_resultat_et_le_bloc_comparaison(self):
        response = self.client.post(reverse("simulateur"), {
            "secteur": "formation",
            "pages": ["tarifs", "inscription"],
            "source": "organique",
            "premiere_visite": "non",
            "nombre_visites": "4+",
            "duree": "longue",
            "interactions": "eleve",
            "retour_page": "oui",
            "cta_consulte": "oui",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Prospect chaud")
        self.assertContains(response, "Analytics classique")
        self.assertContains(response, "PredictNeed IA")
        self.assertContains(response, "Pourquoi ce score")

    def test_post_cree_une_prediction_avec_les_champs_existants_du_modele(self):
        self.assertEqual(PredictionBesoin.objects.count(), 0)
        self.client.post(reverse("simulateur"), {
            "secteur": "saas",
            "pages": ["tarifs"],
            "duree": "moyenne",
        })
        prediction = PredictionBesoin.objects.get()
        self.assertTrue(prediction.profil)
        self.assertTrue(prediction.besoin_probable)
        self.assertIn(prediction.intention, ["Faible", "Moyenne", "Élevée"])
        self.assertIsInstance(prediction.score, int)

    def test_post_cree_un_evenement_utilisateur_rattache_a_la_session(self):
        self.assertEqual(EvenementUtilisateur.objects.count(), 0)
        self.client.post(reverse("simulateur"), {"secteur": "ecommerce", "pages": ["produit"]})
        self.assertEqual(SessionVisiteur.objects.count(), 1)
        evenement = EvenementUtilisateur.objects.get()
        self.assertEqual(evenement.type_evenement, "formulaire")
        self.assertIn("ecommerce", evenement.page)

    def test_secteur_invalide_retombe_sur_le_secteur_par_defaut_sans_erreur(self):
        response = self.client.post(reverse("simulateur"), {"secteur": "inconnu", "pages": []})
        self.assertEqual(response.status_code, 200)
