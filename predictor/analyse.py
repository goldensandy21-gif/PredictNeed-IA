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


# =============================================================================
# Démonstration commerciale du simulateur (/simulateur/)
# =============================================================================
#
# Ce qui suit alimente exclusivement la page /simulateur/ (démonstration
# commerciale à destination des prospects). Cela n'affecte ni
# analyser_besoin() (widget d'accueil) ni analyser_session_automatique()
# (analyse réelle des sessions trackées), qui restent inchangées ci-dessus.
#
# Le score 0-100 produit ici est une simulation pédagogique construite à
# partir de signaux sélectionnés par le visiteur du formulaire — jamais une
# prédiction réelle sur un vrai visiteur.

SECTEURS_SIMULATEUR = {
    "saas": {
        "label": "SaaS / logiciel B2B",
        "pages": [
            {"value": "fonctionnalites", "label": "Fonctionnalités"},
            {"value": "cas_clients", "label": "Cas clients"},
            {"value": "integrations", "label": "Intégrations"},
            {"value": "tarifs", "label": "Tarifs"},
            {"value": "essai", "label": "Essai gratuit"},
        ],
        "page_tarifs": "tarifs",
        "page_conversion": "essai",
        "action": "démarrer un essai gratuit",
    },
    "formation": {
        "label": "Organisme de formation",
        "pages": [
            {"value": "programme", "label": "Programme"},
            {"value": "tarifs", "label": "Tarifs"},
            {"value": "financement", "label": "Financement"},
            {"value": "temoignages", "label": "Témoignages"},
            {"value": "inscription", "label": "Inscription"},
        ],
        "page_tarifs": "tarifs",
        "page_conversion": "inscription",
        "action": "s'inscrire au programme",
    },
    "agence": {
        "label": "Agence / service B2B",
        "pages": [
            {"value": "services", "label": "Services"},
            {"value": "realisations", "label": "Réalisations"},
            {"value": "methode", "label": "Méthode"},
            {"value": "tarifs", "label": "Tarifs"},
            {"value": "devis", "label": "Demande de devis"},
        ],
        "page_tarifs": "tarifs",
        "page_conversion": "devis",
        "action": "demander un devis",
    },
    "conseil": {
        "label": "Conseil",
        "pages": [
            {"value": "expertise", "label": "Domaines d'expertise"},
            {"value": "etudes_de_cas", "label": "Études de cas"},
            {"value": "equipe", "label": "Équipe"},
            {"value": "tarifs", "label": "Tarifs / honoraires"},
            {"value": "rendez_vous", "label": "Prise de rendez-vous"},
        ],
        "page_tarifs": "tarifs",
        "page_conversion": "rendez_vous",
        "action": "prendre rendez-vous",
    },
    "ecommerce": {
        "label": "E-commerce",
        "pages": [
            {"value": "categorie", "label": "Catégorie"},
            {"value": "produit", "label": "Produit"},
            {"value": "avis", "label": "Avis clients"},
            {"value": "livraison", "label": "Livraison"},
            {"value": "panier", "label": "Panier"},
        ],
        "page_tarifs": "produit",
        "page_conversion": "panier",
        "action": "finaliser sa commande",
    },
    "immobilier": {
        "label": "Immobilier",
        "pages": [
            {"value": "annonce", "label": "Annonce"},
            {"value": "quartier", "label": "Quartier / localisation"},
            {"value": "financement", "label": "Simulation de financement"},
            {"value": "avis", "label": "Avis / références"},
            {"value": "contact_agence", "label": "Contact agence"},
        ],
        "page_tarifs": "financement",
        "page_conversion": "contact_agence",
        "action": "contacter l'agence",
    },
}

SECTEUR_PAR_DEFAUT = "saas"

SOURCE_LABELS = {
    "organique": "Recherche organique",
    "payant": "Publicité payante",
    "social": "Réseaux sociaux",
    "email": "Email / newsletter",
    "direct": "Accès direct",
    "referent": "Site référent",
}

NOMBRE_VISITES_LABELS = {
    "1": "1 visite",
    "2-3": "2 à 3 visites",
    "4+": "4 visites ou plus",
}

DUREE_LABELS = {
    "courte": "Courte",
    "moyenne": "Moyenne",
    "longue": "Longue",
}

INTERACTIONS_LABELS = {
    "faible": "Faible",
    "moyen": "Moyen",
    "eleve": "Élevé",
}

# Classes CSS (sans accent) pour "Faible" / "Moyenne" / "Élevée", utilisées à
# la fois pour le niveau d'intention et pour la priorité commerciale.
NIVEAU_SLUGS = {
    "Faible": "faible",
    "Moyenne": "moyenne",
    "Élevée": "elevee",
}

# Détail par profil comportemental : besoin probable (peut contenir "{action}",
# remplacé par l'action de conversion propre au secteur), priorité commerciale
# et recommandation (next best action).
PROFIL_DETAILS = {
    "Visiteur curieux": {
        "besoin": "découvrir ce que propose le site",
        "priorite": "Faible",
        "recommandation": (
            "Continuer à observer le comportement du visiteur ; proposer un "
            "contenu éducatif ou une ressource gratuite avant toute relance commerciale."
        ),
    },
    "Comparateur actif": {
        "besoin": "comparer les offres avant de choisir",
        "priorite": "Moyenne",
        "recommandation": (
            "Mettre en avant un comparatif clair, un avantage différenciant "
            "ou un avis client pour l'aider à trancher."
        ),
    },
    "Visiteur hésitant": {
        "besoin": "être rassuré avant de {action}",
        "priorite": "Moyenne",
        "recommandation": (
            "Si le visiteur est identifié, le relancer avec un message "
            "rassurant ou une preuve sociale ; sinon, répondre aux objections "
            "courantes directement sur la page pour lever le dernier frein."
        ),
    },
    "Prospect chaud": {
        "besoin": "passer à l'action pour {action}",
        "priorite": "Élevée",
        "recommandation": (
            "Si le visiteur est identifié, prioriser une relance rapide ; "
            "sinon, faciliter immédiatement l'étape pour {action}."
        ),
    },
    "Visiteur récurrent": {
        "besoin": "continuer à explorer avant de se décider",
        "priorite": "Moyenne",
        "recommandation": (
            "Si le visiteur est identifié, lui proposer une relance "
            "personnalisée ; sinon, mettre en avant un contenu de suivi pour "
            "maintenir l'intérêt sans brusquer la décision."
        ),
    },
    "Prospect issu de campagne": {
        "besoin": "vérifier que l'offre correspond à ce qui a motivé le clic",
        "priorite": "Moyenne",
        "recommandation": (
            "Aligner le message d'accueil avec la campagne d'origine et "
            "guider vers l'étape suivante la plus pertinente."
        ),
    },
}


def _secteur_config(secteur_key):
    return SECTEURS_SIMULATEUR.get(secteur_key, SECTEURS_SIMULATEUR[SECTEUR_PAR_DEFAUT])


def _label_page(secteur, valeur_page):
    for page in secteur["pages"]:
        if page["value"] == valeur_page:
            return page["label"]
    return valeur_page


def normaliser_signaux(secteur_key, signaux):
    """Ne jamais faire confiance uniquement au JavaScript : filtre, déduplique
    et corrige les incohérences des signaux reçus (typiquement via POST)
    avant tout calcul ou tout réaffichage dans le formulaire.
    """
    secteur = _secteur_config(secteur_key)
    pages_autorisees = [page["value"] for page in secteur["pages"]]

    pages = []
    for page in signaux.get("pages") or []:
        if page in pages_autorisees and page not in pages:
            pages.append(page)

    def _choix_valide(valeur, choix_valides, defaut):
        return valeur if valeur in choix_valides else defaut

    source = _choix_valide(signaux.get("source"), SOURCE_LABELS, "organique")
    duree = _choix_valide(signaux.get("duree"), DUREE_LABELS, "courte")
    interactions = _choix_valide(signaux.get("interactions"), INTERACTIONS_LABELS, "faible")
    nombre_visites = _choix_valide(signaux.get("nombre_visites"), NOMBRE_VISITES_LABELS, "1")

    premiere_visite = "non" if signaux.get("premiere_visite") == "non" else "oui"

    # Cohérence obligatoire entre type de visite et nombre de visites : une
    # première visite ne peut être que la 1ère, et une visite récurrente ne
    # peut pas être comptabilisée comme une visite unique.
    if premiere_visite == "oui":
        nombre_visites = "1"
    elif nombre_visites == "1":
        nombre_visites = "2-3"

    def _case(valeur):
        return "oui" if valeur == "oui" else ""

    return {
        "pages": pages,
        "source": source,
        "premiere_visite": premiere_visite,
        "nombre_visites": nombre_visites,
        "duree": duree,
        "interactions": interactions,
        "retour_page": _case(signaux.get("retour_page")),
        "cta_consulte": _case(signaux.get("cta_consulte")),
        "abandon": _case(signaux.get("abandon")),
    }


# Scénarios rapides exprimés de façon générique (indépendante du secteur) :
# "tarifs" et "conversion" désignent les pages spéciales du secteur choisi,
# "autre" consomme la prochaine page ordinaire disponible. Résolus ensuite
# pour le secteur réellement sélectionné par resoudre_scenario_generique(),
# aussi bien côté template (JSON pour le JS) que côté tests Python.
SCENARIOS_GENERIQUES = {
    "curieux": {
        "pages_roles": ["autre"],
        "source": "organique", "premiere_visite": "oui", "nombre_visites": "1",
        "retour_page": False, "duree": "courte", "interactions": "faible",
        "cta_consulte": False, "abandon": False,
    },
    "comparateur": {
        "pages_roles": ["autre", "tarifs", "autre"],
        "source": "organique", "premiere_visite": "non", "nombre_visites": "2-3",
        "retour_page": True, "duree": "moyenne", "interactions": "moyen",
        "cta_consulte": False, "abandon": False,
    },
    "hesitant": {
        "pages_roles": ["tarifs"],
        "source": "organique", "premiere_visite": "non", "nombre_visites": "2-3",
        "retour_page": True, "duree": "moyenne", "interactions": "faible",
        "cta_consulte": True, "abandon": True,
    },
    "chaud": {
        "pages_roles": ["autre", "autre", "tarifs", "conversion"],
        "source": "organique", "premiere_visite": "non", "nombre_visites": "4+",
        "retour_page": True, "duree": "longue", "interactions": "eleve",
        "cta_consulte": True, "abandon": False,
    },
    "recurrent": {
        "pages_roles": ["autre", "autre"],
        "source": "organique", "premiere_visite": "non", "nombre_visites": "2-3",
        "retour_page": True, "duree": "moyenne", "interactions": "moyen",
        "cta_consulte": False, "abandon": False,
    },
    "campagne": {
        "pages_roles": ["autre"],
        "source": "payant", "premiere_visite": "oui", "nombre_visites": "1",
        "retour_page": False, "duree": "moyenne", "interactions": "moyen",
        "cta_consulte": False, "abandon": False,
    },
}


def resoudre_pages_scenario(secteur_key, pages_roles):
    """Traduit une liste de rôles génériques ("tarifs", "conversion", "autre")
    en pages concrètes du secteur sélectionné."""
    secteur = _secteur_config(secteur_key)
    valeurs_secteur = [page["value"] for page in secteur["pages"]]
    autres = [
        valeur for valeur in valeurs_secteur
        if valeur not in (secteur["page_tarifs"], secteur["page_conversion"])
    ]

    resultat = []
    index_autre = 0
    for role in pages_roles:
        if role == "tarifs":
            resultat.append(secteur["page_tarifs"])
        elif role == "conversion":
            resultat.append(secteur["page_conversion"])
        elif role == "autre" and index_autre < len(autres):
            resultat.append(autres[index_autre])
            index_autre += 1
    return resultat


def resoudre_scenario_generique(nom_scenario, secteur_key):
    """Résout un scénario rapide générique en signaux concrets pour le
    secteur donné (ne force jamais un secteur particulier)."""
    preset = SCENARIOS_GENERIQUES[nom_scenario]
    signaux = {
        "pages": resoudre_pages_scenario(secteur_key, preset["pages_roles"]),
        "source": preset["source"],
        "premiere_visite": preset["premiere_visite"],
        "nombre_visites": preset["nombre_visites"],
        "duree": preset["duree"],
        "interactions": preset["interactions"],
        "retour_page": "oui" if preset["retour_page"] else None,
        "cta_consulte": "oui" if preset["cta_consulte"] else None,
        "abandon": "oui" if preset["abandon"] else None,
    }
    return signaux


def analyser_simulation_avancee(secteur_key, signaux):
    """Simulation pédagogique de la logique de décision de PredictNeed IA.

    `signaux` est un dict de comportements sélectionnés par le visiteur du
    formulaire (pages consultées, source, durée...), jamais un comportement
    réellement observé. Le score et le profil renvoyés sont donc un
    "intention probable" explicable, pas une prédiction certaine.
    """
    secteur = _secteur_config(secteur_key)
    normalises = normaliser_signaux(secteur_key, signaux)

    pages = normalises["pages"]
    source = normalises["source"]
    premiere_visite = normalises["premiere_visite"] == "oui"
    nombre_visites = normalises["nombre_visites"]
    retour_page = normalises["retour_page"] == "oui"
    duree = normalises["duree"]
    interactions = normalises["interactions"]
    cta_consulte = normalises["cta_consulte"] == "oui"
    abandon = normalises["abandon"] == "oui"

    a_page_tarifs = secteur["page_tarifs"] in pages
    a_page_conversion = secteur["page_conversion"] in pages
    plusieurs_pages = len(pages) >= 2

    decomposition = []
    score = 0

    def ajouter(label, points):
        """Applique `points` au score en le gardant dans [0, 100] et
        enregistre dans la décomposition le delta RÉELLEMENT appliqué (pas
        le poids nominal), afin que la somme affichée corresponde toujours
        exactement au score final, y compris dans les cas limites où un
        plafond serait atteint."""
        nonlocal score
        avant = score
        apres = max(0, min(100, score + points))
        delta = apres - avant
        score = apres
        if delta == 0:
            return
        if delta != points:
            label = f"{label} (plafonné)"
        decomposition.append({"label": label, "points": delta})

    # Poids calibrés pour que la somme de toutes les composantes positives
    # compatibles entre elles atteigne au maximum 100 (voir Prospect chaud,
    # qui les cumule toutes) : le plafonnement à 100 ne devrait donc plus
    # jamais se produire en pratique. La source d'acquisition n'apporte pas
    # de points ici : elle sert uniquement à qualifier le profil ("Prospect
    # issu de campagne") et reste visible telle quelle dans le comparatif
    # Analytics classique.
    if a_page_tarifs:
        libelle_tarifs = _label_page(secteur, secteur["page_tarifs"])
        ajouter(f"Consultation d'une page de comparaison / décision (« {libelle_tarifs} »)", 15)
    if a_page_conversion:
        libelle_conversion = _label_page(secteur, secteur["page_conversion"])
        ajouter(f"Page proche de la conversion consultée (« {libelle_conversion} »)", 20)
    if plusieurs_pages:
        ajouter("Plusieurs pages du parcours consultées", 5)
    if retour_page:
        ajouter("Retour sur une page déjà visitée", 10)
    if not premiere_visite:
        ajouter("Visite récurrente (pas une première visite)", 10)
    if nombre_visites == "4+":
        ajouter("Nombre de visites élevé", 10)
    elif nombre_visites == "2-3":
        ajouter("Plusieurs visites", 5)
    if duree == "longue":
        ajouter("Durée de visite élevée", 10)
    elif duree == "moyenne":
        ajouter("Durée de visite moyenne", 5)
    if interactions == "eleve":
        ajouter("Engagement (clics) élevé", 10)
    elif interactions == "moyen":
        ajouter("Engagement modéré", 5)
    if cta_consulte:
        ajouter("Formulaire ou CTA consulté", 10)
    if abandon:
        ajouter("Abandon avant conversion", -15)

    if score >= 70:
        niveau = "Élevée"
    elif score >= 40:
        niveau = "Moyenne"
    else:
        niveau = "Faible"

    if abandon and (a_page_tarifs or a_page_conversion):
        profil = "Visiteur hésitant"
    elif a_page_conversion and (not premiere_visite or nombre_visites in ("2-3", "4+")) and score >= 65:
        profil = "Prospect chaud"
    elif a_page_tarifs and plusieurs_pages and score >= 40:
        profil = "Comparateur actif"
    elif not premiere_visite and nombre_visites in ("2-3", "4+"):
        profil = "Visiteur récurrent"
    elif source in ("payant", "social", "email") and premiere_visite:
        profil = "Prospect issu de campagne"
    else:
        profil = "Visiteur curieux"

    details = PROFIL_DETAILS[profil]
    besoin_probable = details["besoin"].format(action=secteur["action"])
    recommandation = details["recommandation"].format(action=secteur["action"])
    priorite_commerciale = details["priorite"]

    signaux_explicatifs = [
        item["label"] for item in sorted(decomposition, key=lambda item: abs(item["points"]), reverse=True)
    ][:5]

    analytics_classique = {
        "nombre_visites": NOMBRE_VISITES_LABELS.get(nombre_visites, nombre_visites),
        "pages_vues": len(pages),
        "duree": DUREE_LABELS.get(duree, duree),
        "source": SOURCE_LABELS.get(source, source),
    }

    return {
        "secteur_label": secteur["label"],
        "score": score,
        "niveau": niveau,
        "niveau_slug": NIVEAU_SLUGS.get(niveau, "faible"),
        "profil": profil,
        "besoin_probable": besoin_probable,
        "priorite_commerciale": priorite_commerciale,
        "priorite_slug": NIVEAU_SLUGS.get(priorite_commerciale, "faible"),
        "recommandation": recommandation,
        "signaux_explicatifs": signaux_explicatifs,
        "decomposition": decomposition,
        "analytics_classique": analytics_classique,
        "signaux_normalises": normalises,
        "pages_consultees": [
            page_def["label"]
            for page_def in secteur["pages"]
            if page_def["value"] in pages
        ],
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