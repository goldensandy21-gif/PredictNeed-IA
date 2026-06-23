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
        recommandation = "Proposer une offre claire, un tableau comparatif ou une remise limitée."

    elif page_visitee == "produit":
        score += 2
        profil = "Explorateur produit"
        prediction = "Recherche d'information produit"
        recommandation = "Mettre en avant les bénéfices, les avis clients et les détails du produit."

    elif page_visitee == "contact":
        score += 3
        profil = "Besoin d'accompagnement"
        prediction = "Recherche d'aide ou de contact humain"
        recommandation = "Proposer un rendez-vous, un chat ou un accompagnement personnalisé."

    elif page_visitee == "blog":
        score += 1
        profil = "Visiteur curieux"
        prediction = "Recherche d'information"
        recommandation = "Proposer un article complémentaire, une newsletter ou une ressource gratuite."

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

    else:
        intention = "Faible"

    return {
        "profil": profil,
        "prediction": prediction,
        "intention": intention,
        "score": score,
        "recommandation": recommandation,
    }

def analyser_session_automatique(session):
    evenements = session.evenements.all().order_by("date_creation")

    pages_vues = []
    clics = []
    temps_total = 0

    for evenement in evenements:
        if evenement.type_evenement == "page_vue":
            pages_vues.append(evenement.page.lower())

        elif evenement.type_evenement == "clic":
            clics.append((evenement.valeur or "").lower())

        elif evenement.type_evenement == "temps":
            try:
                secondes = int(str(evenement.valeur).split()[0])
                temps_total += secondes
            except:
                pass

    score = 0
    profil = "Visiteur curieux"
    prediction = "Découverte du site"
    recommandation = "Continuer à observer le comportement du visiteur."

    # Analyse des pages visitées
    if any("prix" in page for page in pages_vues):
        score += 2
        profil = "Comparateur"
        prediction = "Comparaison d'offres"
        recommandation = "Mettre en avant une offre claire ou un tableau comparatif."

    if any("produit" in page for page in pages_vues):
        score += 2
        profil = "Explorateur produit"
        prediction = "Recherche d'information produit"
        recommandation = "Proposer une fiche détaillée ou une recommandation personnalisée."

    if any("contact" in page for page in pages_vues):
        score += 3
        profil = "Besoin d'accompagnement"
        prediction = "Besoin de contact ou d'assistance"
        recommandation = "Proposer un rendez-vous, un chat ou un échange direct."

    # Analyse du temps passé
    if temps_total >= 60:
        score += 2
    elif temps_total >= 20:
        score += 1

    # Analyse des clics
    if len(clics) >= 3:
        score += 2
    elif len(clics) >= 1:
        score += 1

    if any("analyse" in clic or "analyser" in clic for clic in clics):
        score += 2
        profil = "Visiteur engagé"
        prediction = "Intérêt actif pour l'analyse"
        recommandation = "Proposer une démonstration ou une offre personnalisée."

    if any("commencer" in clic for clic in clics):
        score += 1

    # Déduction de l'intention
    if score >= 6:
        intention = "Forte"
        profil = "Prêt à acheter"
        recommandation = "Proposer une offre claire, un tableau comparatif ou une remise limitée."
    elif score >= 3:
        intention = "Moyenne"
    else:
        intention = "Faible"

    return {
        "profil": profil,
        "prediction": prediction,
        "intention": intention,
        "score": score,
        "recommandation": recommandation,
    }