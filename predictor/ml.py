
import math

from .models import ModeleMachineLearning


FEATURE_NAMES = [
    "log_pages_vues",
    "log_clics",
    "log_temps_secondes",
    "est_rebond",
    "est_mobile",
    "est_tablette",
    "campagne_utm",
    "page_prix",
    "page_contact",
    "page_produit",
    "page_guide",
]


def _events_for_session(session):
    prefetched = getattr(session, "ml_evenements", None)
    if prefetched is not None:
        return prefetched
    return list(session.evenements.all())


def extraire_caracteristiques(session):
    pages = []
    for evenement in _events_for_session(session):
        if evenement.type_evenement == "page_vue":
            pages.append((evenement.page or "").lower())

    return {
        "log_pages_vues": math.log1p(float(session.nombre_pages_vues or 0)),
        "log_clics": math.log1p(float(session.nombre_clics or 0)),
        "log_temps_secondes": math.log1p(
            min(float(session.temps_total_secondes or 0), 86400.0)
        ),
        "est_rebond": 1.0 if session.est_rebond else 0.0,
        "est_mobile": 1.0 if session.est_mobile else 0.0,
        "est_tablette": 1.0 if session.est_tablette else 0.0,
        "campagne_utm": 1.0 if (session.utm_source or session.utm_campaign) else 0.0,
        "page_prix": 1.0 if any(
            "prix" in page or "tarif" in page for page in pages
        ) else 0.0,
        "page_contact": 1.0 if any(
            "contact" in page or "rendez" in page for page in pages
        ) else 0.0,
        "page_produit": 1.0 if any(
            "produit" in page
            or "offre" in page
            or "service" in page
            for page in pages
        ) else 0.0,
        "page_guide": 1.0 if any(
            "guide" in page or "blog" in page for page in pages
        ) else 0.0,
    }


def vecteur_caracteristiques(session, noms=None):
    noms = noms or FEATURE_NAMES
    valeurs = extraire_caracteristiques(session)
    return [float(valeurs.get(nom, 0.0)) for nom in noms]


def _sigmoid(value):
    value = max(min(float(value), 40.0), -40.0)
    return 1.0 / (1.0 + math.exp(-value))


def predire_probabilite(session):
    if session.site_id is None:
        return None

    modele = (
        ModeleMachineLearning.objects
        .filter(site_id=session.site_id, actif=True)
        .order_by("-date_entrainement")
        .first()
    )
    if modele is None:
        return None

    vecteur = vecteur_caracteristiques(
        session,
        modele.noms_caracteristiques,
    )
    coefficients = [float(value) for value in modele.coefficients]
    moyennes = [float(value) for value in modele.moyennes_caracteristiques]
    echelles = [float(value) for value in modele.echelles_caracteristiques]

    if not (
        len(vecteur)
        == len(coefficients)
        == len(moyennes)
        == len(echelles)
    ):
        return None

    standardise = []
    for valeur, moyenne, echelle in zip(vecteur, moyennes, echelles):
        echelle_sure = echelle if abs(echelle) > 1e-12 else 1.0
        standardise.append((valeur - moyenne) / echelle_sure)

    linear = float(modele.intercept)
    linear += sum(
        coefficient * valeur
        for coefficient, valeur in zip(coefficients, standardise)
    )
    probabilite = _sigmoid(linear)

    return {
        "probabilite": probabilite,
        "version": modele.version,
        "seuil_intention_forte": float(modele.seuil_intention_forte),
        "metriques": modele.metriques,
    }
