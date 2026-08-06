
import logging

logger = logging.getLogger(__name__)


def analyser_besoin(page_visitee, temps, clics):
    score = 0
    prediction = "Besoin non identifié"
    intention = "Faible"
    profil = "Visiteur curieux"
    recommandation = "Observer davantage le comportement de l'utilisateur."

    if page_visitee == "prix":
        score += 2
        profil = "Comparateur"
        prediction = "Comparaison d'offres"
        recommandation = (
            "Proposer une offre claire, un tableau comparatif "
            "ou une remise limitée."
        )
    elif page_visitee == "produit":
        score += 2
        profil = "Explorateur produit"
        prediction = "Recherche d'information produit"
        recommandation = (
            "Mettre en avant les bénéfices, les avis clients "
            "et les détails du produit."
        )
    elif page_visitee == "contact":
        score += 3
        profil = "Besoin d'accompagnement"
        prediction = "Recherche d'aide ou de contact humain"
        recommandation = (
            "Proposer un rendez-vous, un chat "
            "ou un accompagnement personnalisé."
        )
    elif page_visitee == "blog":
        score += 1
        profil = "Visiteur curieux"
        prediction = "Recherche d'information"
        recommandation = (
            "Proposer un article complémentaire, "
            "une newsletter ou une ressource gratuite."
        )

    if temps == "long":
        score += 2
    elif temps == "moyen":
        score += 1

    if clics == "eleve":
        score += 2
    elif clics == "moyen":
        score += 1

    if score >= 6:
        intention = "Forte"
        profil = "Prêt à acheter"
    elif score >= 3:
        intention = "Moyenne"

    return {
        "profil": profil,
        "prediction": prediction,
        "intention": intention,
        "score": score,
        "recommandation": recommandation,
        "moteur": "regles",
        "probabilite_conversion": None,
        "version_modele": "",
    }


def analyser_session_automatique(session):
    evenements = session.evenements.all().order_by("date_creation")
    pages_vues = []
    clics = []
    temps_total = 0

    for evenement in evenements:
        if evenement.type_evenement == "page_vue":
            pages_vues.append((evenement.page or "").lower())
        elif evenement.type_evenement == "clic":
            clics.append((evenement.valeur or "").lower())
        elif evenement.type_evenement == "temps":
            try:
                secondes = int(str(evenement.valeur).split()[0])
                temps_total += secondes
            except (TypeError, ValueError, IndexError):
                continue

    score = 0
    profil = "Visiteur curieux"
    prediction = "Découverte du site"
    recommandation = "Continuer à observer le comportement du visiteur."

    if any("prix" in page or "tarif" in page for page in pages_vues):
        score += 2
        profil = "Comparateur"
        prediction = "Comparaison d'offres"
        recommandation = (
            "Mettre en avant une offre claire ou un tableau comparatif."
        )

    if any(
        "produit" in page
        or "offre" in page
        or "service" in page
        for page in pages_vues
    ):
        score += 2
        profil = "Explorateur produit"
        prediction = "Recherche d'information produit"
        recommandation = (
            "Proposer une fiche détaillée "
            "ou une recommandation personnalisée."
        )

    if any("contact" in page or "rendez" in page for page in pages_vues):
        score += 3
        profil = "Besoin d'accompagnement"
        prediction = "Besoin de contact ou d'assistance"
        recommandation = (
            "Proposer un rendez-vous, un chat ou un échange direct."
        )

    if temps_total >= 60:
        score += 2
    elif temps_total >= 20:
        score += 1

    if len(clics) >= 3:
        score += 2
    elif len(clics) >= 1:
        score += 1

    if any("analyse" in clic or "analyser" in clic for clic in clics):
        score += 2
        profil = "Visiteur engagé"
        prediction = "Intérêt actif pour l'analyse"
        recommandation = (
            "Proposer une démonstration ou une offre personnalisée."
        )

    if any("commencer" in clic for clic in clics):
        score += 1

    if score >= 6:
        intention = "Forte"
        profil = "Prêt à acheter"
        recommandation = (
            "Proposer une offre claire, un tableau comparatif "
            "ou un contact rapide."
        )
    elif score >= 3:
        intention = "Moyenne"
    else:
        intention = "Faible"

    resultat = {
        "profil": profil,
        "prediction": prediction,
        "intention": intention,
        "score": score,
        "recommandation": recommandation,
        "moteur": "regles",
        "probabilite_conversion": None,
        "version_modele": "",
    }

    try:
        from .ml import predire_probabilite

        prediction_ml = predire_probabilite(session)
    except Exception:
        logger.exception(
            "Le modèle ML n'a pas pu être appliqué à la session %s.",
            session.pk,
        )
        prediction_ml = None

    if prediction_ml is None:
        return resultat

    probabilite = float(prediction_ml["probabilite"])
    resultat["moteur"] = "machine_learning"
    resultat["probabilite_conversion"] = probabilite
    resultat["version_modele"] = prediction_ml["version"]
    resultat["score"] = max(0, min(10, round(probabilite * 10)))

    if probabilite >= prediction_ml["seuil_intention_forte"]:
        resultat["intention"] = "Forte"
        resultat["profil"] = "Prospect prioritaire"
        resultat["prediction"] = "Probabilité de conversion élevée"
        resultat["recommandation"] = (
            "Prioriser une prise de contact humaine "
            "et vérifier le contexte avant toute décision."
        )
    elif probabilite >= 0.35:
        resultat["intention"] = "Moyenne"
        resultat["prediction"] = "Probabilité de conversion intermédiaire"
    else:
        resultat["intention"] = "Faible"
        resultat["prediction"] = "Probabilité de conversion faible"

    return resultat
