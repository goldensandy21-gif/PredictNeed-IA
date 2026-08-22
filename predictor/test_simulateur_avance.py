"""Tests de la démonstration commerciale du simulateur (/simulateur/).

Ces tests couvrent uniquement la nouvelle logique ajoutée pour transformer
/simulateur/ en démonstration commerciale : analyser_simulation_avancee(),
normaliser_signaux(), resoudre_scenario_generique() et le rendu de la vue
simulateur().

Ils ne touchent ni analyser_besoin() (widget d'accueil) ni
analyser_session_automatique() (analyse réelle des sessions trackées) :
ces deux fonctions restent inchangées et ne sont pas re-testées ici.
"""
import re

from django.test import TestCase
from django.urls import reverse

from predictor.analyse import (
    SCENARIOS_GENERIQUES,
    SECTEUR_PAR_DEFAUT,
    SECTEURS_SIMULATEUR,
    analyser_simulation_avancee,
    normaliser_signaux,
    resoudre_scenario_generique,
)
from predictor.models import EvenementUtilisateur, PredictionBesoin, SessionVisiteur


# ---------------------------------------------------------------------------
# Les scénarios rapides sont résolus dynamiquement via
# resoudre_scenario_generique() : c'est la SEULE source de vérité, partagée
# avec le JS de simulateur.html (SCENARIOS_GENERIQUES exposé en JSON). Les
# tests n'entretiennent donc jamais une copie séparée qui pourrait diverger.
# ---------------------------------------------------------------------------

SCENARIOS_ET_NIVEAUX_ATTENDUS_SAAS = [
    ("curieux", "Visiteur curieux", "Faible", 0),
    ("comparateur", "Comparateur actif", "Moyenne", 55),
    ("hesitant", "Visiteur hésitant", "Moyenne", 40),
    ("chaud", "Prospect chaud", "Élevée", 100),
    ("recurrent", "Visiteur récurrent", "Moyenne", 40),
    ("campagne", "Prospect issu de campagne", "Faible", 10),
]


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

    def test_chaque_scenario_a_le_profil_le_niveau_et_le_score_attendus(self):
        for nom, profil_attendu, niveau_attendu, score_attendu in SCENARIOS_ET_NIVEAUX_ATTENDUS_SAAS:
            signaux = resoudre_scenario_generique(nom, "saas")
            resultat = analyser_simulation_avancee("saas", signaux)
            self.assertEqual(resultat["profil"], profil_attendu, nom)
            self.assertEqual(resultat["niveau"], niveau_attendu, nom)
            self.assertEqual(resultat["score"], score_attendu, nom)

    def test_les_6_scenarios_couvrent_les_3_niveaux_naturellement(self):
        """Ne doit jamais tous atterrir sur le même niveau (le vrai bug
        signalé était que tout semblait extrême à cause du plafonnage
        silencieux à 100)."""
        niveaux = {niveau for _, _, niveau, _ in SCENARIOS_ET_NIVEAUX_ATTENDUS_SAAS}
        self.assertEqual(niveaux, {"Faible", "Moyenne", "Élevée"})

    def test_scenario_prospect_chaud_priorite_elevee(self):
        signaux = resoudre_scenario_generique("chaud", "saas")
        resultat = analyser_simulation_avancee("saas", signaux)
        self.assertEqual(resultat["priorite_commerciale"], "Élevée")


# ---------------------------------------------------------------------------
# A. Les scénarios doivent s'adapter au secteur COURANT, jamais forcer "saas".
# ---------------------------------------------------------------------------

class ScenariosAdaptesAuSecteurTests(TestCase):
    def test_formation_prospect_chaud_conserve_le_secteur_formation(self):
        signaux = resoudre_scenario_generique("chaud", "formation")
        resultat = analyser_simulation_avancee("formation", signaux)

        self.assertEqual(resultat["secteur_label"], SECTEURS_SIMULATEUR["formation"]["label"])
        self.assertEqual(resultat["profil"], "Prospect chaud")

        pages_formation = {p["value"] for p in SECTEURS_SIMULATEUR["formation"]["pages"]}
        for page in signaux["pages"]:
            self.assertIn(page, pages_formation)
        # Les pages spéciales du secteur formation doivent être utilisées,
        # jamais celles de saas ("essai", "fonctionnalites"...).
        self.assertIn("tarifs", signaux["pages"])
        self.assertIn("inscription", signaux["pages"])
        self.assertNotIn("essai", signaux["pages"])
        self.assertNotIn("fonctionnalites", signaux["pages"])

    def test_ecommerce_comparateur_actif_utilise_les_pages_ecommerce(self):
        signaux = resoudre_scenario_generique("comparateur", "ecommerce")
        resultat = analyser_simulation_avancee("ecommerce", signaux)

        self.assertEqual(resultat["profil"], "Comparateur actif")
        pages_ecommerce = {p["value"] for p in SECTEURS_SIMULATEUR["ecommerce"]["pages"]}
        for page in signaux["pages"]:
            self.assertIn(page, pages_ecommerce)
        # "produit" est l'équivalent "tarifs" du secteur e-commerce : le
        # secteur ne possède même pas de page littéralement nommée "tarifs".
        self.assertIn("produit", signaux["pages"])
        self.assertNotIn("tarifs", pages_ecommerce)

    def test_tous_les_secteurs_resolvent_le_scenario_chaud_sans_page_orpheline(self):
        """Filet de sécurité : pour chaque secteur, chaque rôle générique
        (tarifs/conversion/autre) doit se résoudre vers une page qui existe
        réellement dans le catalogue de CE secteur."""
        for secteur_key in SECTEURS_SIMULATEUR:
            for nom_scenario in SCENARIOS_GENERIQUES:
                signaux = resoudre_scenario_generique(nom_scenario, secteur_key)
                pages_valides = {p["value"] for p in SECTEURS_SIMULATEUR[secteur_key]["pages"]}
                for page in signaux["pages"]:
                    self.assertIn(page, pages_valides, (secteur_key, nom_scenario))


class DecompositionCoherenteAvecLeScoreTests(TestCase):
    """Règle obligatoire : la somme des points affichés dans la
    décomposition doit toujours être strictement égale au score final
    affiché, y compris dans les cas limites où un plafond serait atteint."""

    def test_somme_de_la_decomposition_egale_le_score_pour_les_6_scenarios(self):
        for nom, *_ in SCENARIOS_ET_NIVEAUX_ATTENDUS_SAAS:
            signaux = resoudre_scenario_generique(nom, "saas")
            resultat = analyser_simulation_avancee("saas", signaux)
            somme = sum(item["points"] for item in resultat["decomposition"])
            self.assertEqual(somme, resultat["score"], nom)

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


# ---------------------------------------------------------------------------
# C. Normalisation serveur — ne jamais faire confiance uniquement au JS.
# ---------------------------------------------------------------------------

class NormalisationServeurTests(TestCase):
    def test_pages_hors_catalogue_du_secteur_sont_filtrees(self):
        normalises = normaliser_signaux("saas", {"pages": ["tarifs", "produit", "n_importe_quoi"]})
        self.assertEqual(normalises["pages"], ["tarifs"])

    def test_pages_dupliquees_sont_dedupliquees_en_conservant_l_ordre(self):
        normalises = normaliser_signaux("saas", {"pages": ["tarifs", "essai", "tarifs", "essai"]})
        self.assertEqual(normalises["pages"], ["tarifs", "essai"])

    def test_valeurs_de_choix_invalides_retombent_sur_un_defaut_sur(self):
        normalises = normaliser_signaux("saas", {
            "source": "hackeur", "duree": "infinie",
            "interactions": "maximale", "nombre_visites": "beaucoup",
        })
        self.assertEqual(normalises["source"], "organique")
        self.assertEqual(normalises["duree"], "courte")
        self.assertEqual(normalises["interactions"], "faible")
        self.assertEqual(normalises["nombre_visites"], "1")

    def test_premiere_visite_oui_impose_nombre_visites_egal_a_1(self):
        normalises = normaliser_signaux("saas", {"premiere_visite": "oui", "nombre_visites": "4+"})
        self.assertEqual(normalises["nombre_visites"], "1")

    def test_visite_recurrente_ne_peut_pas_etre_comptee_comme_une_seule_visite(self):
        normalises = normaliser_signaux("saas", {"premiere_visite": "non", "nombre_visites": "1"})
        self.assertNotEqual(normalises["nombre_visites"], "1")
        self.assertIn(normalises["nombre_visites"], ("2-3", "4+"))

    def test_visite_recurrente_avec_nombre_de_visites_deja_coherent_est_conservee(self):
        normalises = normaliser_signaux("saas", {"premiere_visite": "non", "nombre_visites": "4+"})
        self.assertEqual(normalises["nombre_visites"], "4+")

    def test_cases_a_cocher_ne_prennent_que_oui_ou_vide(self):
        normalises = normaliser_signaux("saas", {"retour_page": "true", "cta_consulte": "1", "abandon": "oui"})
        self.assertEqual(normalises["retour_page"], "")
        self.assertEqual(normalises["cta_consulte"], "")
        self.assertEqual(normalises["abandon"], "oui")

    def test_analyser_simulation_avancee_normalise_avant_de_calculer(self):
        """La normalisation doit s'appliquer même si l'appelant ne l'a pas
        fait explicitement : analyser_simulation_avancee() ne fait jamais
        confiance à ses signaux d'entrée."""
        resultat = analyser_simulation_avancee("saas", {
            "pages": ["tarifs", "tarifs", "page-inexistante"],
            "premiere_visite": "oui",
            "nombre_visites": "4+",
            "source": "inconnue",
        })
        self.assertEqual(resultat["signaux_normalises"]["pages"], ["tarifs"])
        self.assertEqual(resultat["signaux_normalises"]["nombre_visites"], "1")
        self.assertEqual(resultat["signaux_normalises"]["source"], "organique")

    def test_post_avec_des_pages_dun_autre_secteur_est_filtre_cote_serveur(self):
        """Un POST manuel (contournant le JS) ne doit jamais pouvoir injecter
        des pages n'appartenant pas au secteur sélectionné."""
        response = self.client.post(reverse("simulateur"), {
            "secteur": "saas",
            "pages": ["produit", "financement", "tarifs"],  # produit/financement = autres secteurs
        })
        self.assertEqual(response.status_code, 200)
        prediction = PredictionBesoin.objects.get()
        # Seule "tarifs" (page saas) a pu compter : le score ne doit refléter
        # qu'une seule page valide, pas trois.
        self.assertLess(prediction.score, 40)


# ---------------------------------------------------------------------------
# D. Libellés sectoriels honnêtes + formulations qui ne présument jamais
# qu'un visiteur anonyme est identifiable.
# ---------------------------------------------------------------------------

class TexteSectorielEtVisiteurAnonymeTests(TestCase):
    def test_libelle_de_decomposition_utilise_la_vraie_page_du_secteur_ecommerce(self):
        resultat = analyser_simulation_avancee("ecommerce", {"pages": ["produit"]})
        libelles = " ".join(item["label"] for item in resultat["decomposition"])
        self.assertIn("Produit", libelles)
        self.assertNotIn("page tarifs", libelles.lower())

    def test_libelle_de_decomposition_utilise_la_vraie_page_du_secteur_immobilier(self):
        resultat = analyser_simulation_avancee("immobilier", {"pages": ["financement", "contact_agence"]})
        libelles = " ".join(item["label"] for item in resultat["decomposition"])
        self.assertIn("Simulation de financement", libelles)
        self.assertIn("Contact agence", libelles)
        self.assertNotIn("page tarifs", libelles.lower())

    def test_aucune_recommandation_ne_presume_un_visiteur_identifiable(self):
        """Aucune formulation du type "Contacter ce prospect" (qui suppose
        que l'on peut déjà joindre ce visiteur) ne doit apparaître : la
        recommandation doit être conditionnelle à l'identification."""
        for nom in SCENARIOS_GENERIQUES:
            signaux = resoudre_scenario_generique(nom, "saas")
            resultat = analyser_simulation_avancee("saas", signaux)
            self.assertNotIn("Contacter ce prospect", resultat["recommandation"], nom)

    def test_recommandation_hesitant_et_chaud_et_recurrent_sont_conditionnelles(self):
        for nom in ("hesitant", "chaud", "recurrent"):
            signaux = resoudre_scenario_generique(nom, "saas")
            resultat = analyser_simulation_avancee("saas", signaux)
            self.assertIn("identifié", resultat["recommandation"], nom)
            self.assertIn("sinon", resultat["recommandation"], nom)


class AnalyserSimulationAvanceeStructureTests(TestCase):
    def test_score_est_borne_entre_0_et_100(self):
        signaux = resoudre_scenario_generique("chaud", "saas")
        resultat = analyser_simulation_avancee("saas", signaux)
        self.assertGreaterEqual(resultat["score"], 0)
        self.assertLessEqual(resultat["score"], 100)

        resultat_vide = analyser_simulation_avancee("saas", {})
        self.assertGreaterEqual(resultat_vide["score"], 0)

    def test_secteur_inconnu_retombe_sur_le_secteur_par_defaut(self):
        signaux = resoudre_scenario_generique("curieux", "saas")
        resultat = analyser_simulation_avancee("secteur-qui-nexiste-pas", signaux)
        self.assertEqual(
            resultat["secteur_label"],
            SECTEURS_SIMULATEUR[SECTEUR_PAR_DEFAUT]["label"],
        )

    def test_decomposition_et_signaux_explicatifs_sont_coherents(self):
        signaux = resoudre_scenario_generique("chaud", "saas")
        resultat = analyser_simulation_avancee("saas", signaux)
        self.assertGreater(len(resultat["decomposition"]), 0)
        self.assertLessEqual(len(resultat["signaux_explicatifs"]), 5)
        labels_decomposition = {item["label"] for item in resultat["decomposition"]}
        for signal in resultat["signaux_explicatifs"]:
            self.assertIn(signal, labels_decomposition)

    def test_abandon_ajoute_un_point_negatif_explicite(self):
        signaux = resoudre_scenario_generique("hesitant", "saas")
        resultat = analyser_simulation_avancee("saas", signaux)
        points_abandon = [
            item["points"] for item in resultat["decomposition"]
            if item["label"] == "Abandon avant conversion"
        ]
        self.assertEqual(points_abandon, [-15])

    def test_besoin_et_recommandation_utilisent_action_du_secteur(self):
        signaux = resoudre_scenario_generique("hesitant", "formation")
        resultat = analyser_simulation_avancee("formation", signaux)
        self.assertIn("s'inscrire au programme", resultat["besoin_probable"])

    def test_analytics_classique_reflete_les_signaux_bruts(self):
        signaux = resoudre_scenario_generique("chaud", "saas")
        resultat = analyser_simulation_avancee("saas", signaux)
        self.assertEqual(resultat["analytics_classique"]["pages_vues"], 4)
        self.assertEqual(resultat["analytics_classique"]["duree"], "Longue")

    def test_aucune_donnee_fictive_presentee_comme_reelle(self):
        """Aucun texte du résultat ne doit prétendre à une certitude absolue."""
        signaux = resoudre_scenario_generique("chaud", "saas")
        resultat = analyser_simulation_avancee("saas", signaux)
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


# ---------------------------------------------------------------------------
# B. Le formulaire doit rester rempli après la soumission, sans contradiction
# avec le résultat affiché.
# ---------------------------------------------------------------------------

class FormulaireConserveApresPostTests(TestCase):
    def setUp(self):
        self.response = self.client.post(reverse("simulateur"), {
            "secteur": "formation",
            "pages": ["tarifs", "inscription"],
            "source": "payant",
            "premiere_visite": "non",
            "nombre_visites": "4+",
            "duree": "longue",
            "interactions": "eleve",
            "retour_page": "oui",
            "cta_consulte": "oui",
            "abandon": "oui",
        })
        self.contenu = self.response.content.decode()

    def test_secteur_soumis_reste_selectionne(self):
        self.assertRegex(self.contenu, r'<option value="formation"[^>]*selected')

    def test_pages_soumises_restent_cochees(self):
        self.assertRegex(self.contenu, r'name="pages" value="tarifs"[^>]*checked')
        self.assertRegex(self.contenu, r'name="pages" value="inscription"[^>]*checked')

    def test_page_non_soumise_du_meme_secteur_reste_decochee(self):
        match = re.search(r'name="pages" value="programme"[^>]*>', self.contenu)
        self.assertIsNotNone(match)
        self.assertNotIn("checked", match.group(0))

    def test_source_soumise_reste_selectionnee(self):
        self.assertRegex(self.contenu, r'<option value="payant"[^>]*selected')

    def test_type_de_visite_soumis_reste_selectionne(self):
        self.assertRegex(self.contenu, r'<option value="non"[^>]*selected[^>]*>Visite récurrente')

    def test_nombre_de_visites_soumis_reste_selectionne(self):
        self.assertRegex(self.contenu, r'<option value="4\+"[^>]*selected')

    def test_duree_soumise_reste_selectionnee(self):
        self.assertRegex(self.contenu, r'<option value="longue"[^>]*selected')

    def test_interactions_soumises_restent_selectionnees(self):
        self.assertRegex(self.contenu, r'<option value="eleve"[^>]*selected')

    def test_cases_a_cocher_standalone_restent_cochees(self):
        self.assertRegex(self.contenu, r'id="retour-page-checkbox"[^>]*checked')
        self.assertRegex(self.contenu, r'id="cta-consulte-checkbox"[^>]*checked')
        self.assertRegex(self.contenu, r'id="abandon-checkbox"[^>]*checked')

    def test_aucune_contradiction_entre_le_formulaire_reaffiche_et_le_resultat(self):
        """Le secteur du <select> réaffiché doit être celui utilisé pour
        calculer le résultat visible juste en dessous."""
        self.assertRegex(self.contenu, r'<option value="formation"[^>]*selected')
        self.assertIn("Organisme de formation", self.contenu)
