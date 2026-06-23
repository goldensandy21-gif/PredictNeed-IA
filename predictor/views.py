from django.shortcuts import render, redirect
from django.db.models import Count
from .analyse import analyser_besoin, analyser_session_automatique
from .models import ClientProfessionnel, SiteClient, SessionVisiteur, EvenementUtilisateur, PredictionBesoin, LeadCapture
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth import get_user_model
from django.urls import reverse


def accueil(request):
    resultat = None

    # Créer une session Django si elle n'existe pas encore
    if not request.session.session_key:
        request.session.create()

    session_id = request.session.session_key

    session_visiteur, created = SessionVisiteur.objects.get_or_create(
        session_id=session_id
    )

    if request.method == "POST":
        page_visitee = request.POST.get("page_visitee")
        temps = request.POST.get("temps")
        clics = request.POST.get("clics")

        resultat = analyser_besoin(page_visitee, temps, clics)

        EvenementUtilisateur.objects.create(
            session=session_visiteur,
            type_evenement="formulaire",
            page=page_visitee,
            valeur=f"Temps : {temps} | Clics : {clics}"
        )

        PredictionBesoin.objects.create(
            session=session_visiteur,
            profil=resultat["profil"],
            besoin_probable=resultat["prediction"],
            intention=resultat["intention"],
            score=resultat["score"],
            recommandation=resultat["recommandation"]
        )

    return render(request, "predictor/accueil.html", resultat or {})

@login_required
def dashboard(request):
    client = getattr(request.user, "client_professionnel", None)

    if request.user.is_superuser and client is None:
        sites = SiteClient.objects.all()
        sessions = SessionVisiteur.objects.all()
        predictions = PredictionBesoin.objects.all()
        leads = LeadCapture.objects.all()
        nom_client = "Administration globale"

    elif client is not None:
        sites = client.sites.all()
        sessions = SessionVisiteur.objects.filter(site__in=sites)
        predictions = PredictionBesoin.objects.filter(session__in=sessions)
        leads = LeadCapture.objects.filter(site__in=sites)
        nom_client = client.nom_entreprise

    else:
        sites = SiteClient.objects.none()
        sessions = SessionVisiteur.objects.none()
        predictions = PredictionBesoin.objects.none()
        leads = LeadCapture.objects.none()
        nom_client = "Aucun espace professionnel associé"

    total_sites = sites.count()
    total_predictions = predictions.count()
    total_sessions = sessions.count()
    total_leads = leads.count()
    intentions_fortes = predictions.filter(intention="Forte").count()

    profils = (
        predictions
        .values("profil")
        .annotate(total=Count("id"))
        .order_by("-total")
    )

    dernieres_predictions = predictions.order_by("-date_creation")[:5]

    leads_chauds = leads.order_by("-score", "-date_creation")[:5]

    base_url = request.build_absolute_uri("/").rstrip("/")

    scripts_installation = []
    sites_onboarding = []

    for site in sites:
        nb_sessions_site = sessions.filter(site=site).count()
        nb_leads_site = leads.filter(site=site).count()

        site_est_actif = nb_sessions_site > 0

        if site_est_actif:
                statut_site = "Site actif"
        else:
            statut_site = "En attente d’installation"

        script = f'''<script
        src="{base_url}/static/predictor/tracker.js"
        data-api-key="{site.cle_api}"
        data-api-url="{base_url}/api/track/"
        data-lead-url="{base_url}/api/lead/">
    </script>'''

    scripts_installation.append({
        "site": site,
        "script": script,
    })

    sites_onboarding.append({
        "site": site,
        "statut": statut_site,
        "est_actif": site_est_actif,
        "nb_sessions": nb_sessions_site,
        "nb_leads": nb_leads_site,
    })

    a_un_site = total_sites > 0
    a_installation_active = total_sessions > 0
    a_lead_capture = total_leads > 0


    return render(request, "predictor/dashboard.html", {
        "nom_client": nom_client,
        "total_sites": total_sites,
        "total_predictions": total_predictions,
        "total_sessions": total_sessions,
        "total_leads": total_leads,
        "intentions_fortes": intentions_fortes,
        "profils": profils,
        "dernieres_predictions": dernieres_predictions,
        "leads_chauds": leads_chauds,
        "scripts_installation": scripts_installation,
        "sites_onboarding": sites_onboarding,
        "a_un_site": a_un_site,
        "a_installation_active": a_installation_active,
        "a_lead_capture": a_lead_capture,
    })

@login_required
def nettoyer_evenements(request):
    if request.method != "POST":
        return redirect("dashboard")

    client = getattr(request.user, "client_professionnel", None)

    if request.user.is_superuser and client is None:
        EvenementUtilisateur.objects.all().delete()

    elif client is not None:
        sites = client.sites.all()
        sessions = SessionVisiteur.objects.filter(site__in=sites)

        EvenementUtilisateur.objects.filter(session__in=sessions).delete()

    return redirect("dashboard")

@login_required
def changer_statut_lead(request, lead_id, nouveau_statut):
    if request.method != "POST":
        return JsonResponse({
            "success": False,
            "error": "Méthode non autorisée"
        }, status=405)

    statuts_valides = ["nouveau", "contacte", "converti", "perdu"]

    if nouveau_statut not in statuts_valides:
        return JsonResponse({
            "success": False,
            "error": "Statut invalide"
        }, status=400)

    client = getattr(request.user, "client_professionnel", None)

    if request.user.is_superuser and client is None:
        lead = LeadCapture.objects.filter(id=lead_id).first()

    elif client is not None:
        sites = client.sites.all()
        lead = LeadCapture.objects.filter(id=lead_id, site__in=sites).first()

    else:
        lead = None

    if lead is None:
        return JsonResponse({
            "success": False,
            "error": "Lead introuvable"
        }, status=404)

    lead.statut_suivi = nouveau_statut
    lead.save()

    return JsonResponse({
        "success": True,
        "statut": lead.statut_suivi,
        "label": lead.get_statut_suivi_display(),
    })

@login_required
def ajouter_site(request):
    client = getattr(request.user, "client_professionnel", None)

    if client is None:
        return redirect("dashboard")

    erreur = None

    if request.method == "POST":
        nom_site = request.POST.get("nom_site")
        domaine = request.POST.get("domaine")

        if not nom_site or not domaine:
            erreur = "Le nom du site et le domaine sont obligatoires."
        else:
            SiteClient.objects.create(
                client=client,
                nom_site=nom_site,
                domaine=domaine
            )

            return redirect("dashboard")

    return render(request, "predictor/ajouter_site.html", {
        "erreur": erreur,
    })

@csrf_exempt
def track_event(request):
    if request.method != "POST":
        return JsonResponse(
            {"success": False, "error": "Méthode non autorisée"},
            status=405
        )

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse(
            {"success": False, "error": "Données JSON invalides"},
            status=400
        )

    api_key = data.get("api_key")
    session_id = data.get("session_id")
    type_evenement = data.get("type_evenement", "page_vue")
    page = data.get("page", "")
    valeur = data.get("valeur", "")

    if not api_key:
        return JsonResponse(
            {"success": False, "error": "Clé API manquante"},
            status=400
        )

    if not session_id:
        return JsonResponse(
            {"success": False, "error": "Session visiteur manquante"},
            status=400
        )

    try:
        site = SiteClient.objects.get(cle_api=api_key, actif=True)
    except SiteClient.DoesNotExist:
        return JsonResponse(
            {"success": False, "error": "Clé API invalide"},
            status=403
        )

    session_visiteur, created = SessionVisiteur.objects.get_or_create(
        site=site,
        session_id=session_id
    )

    EvenementUtilisateur.objects.create(
        session=session_visiteur,
        type_evenement=type_evenement,
        page=page,
        valeur=valeur
    )

    resultat_auto = analyser_session_automatique(session_visiteur)

    if resultat_auto["score"] >= 2:
        PredictionBesoin.objects.create(
            session=session_visiteur,
            profil=resultat_auto["profil"],
            besoin_probable=resultat_auto["prediction"],
            intention=resultat_auto["intention"],
            score=resultat_auto["score"],
            recommandation=resultat_auto["recommandation"]
        )

    return JsonResponse({
    "success": True,
    "message": "Événement enregistré",
    "site": site.nom_site,
    "session": session_visiteur.session_id,
    "prediction": resultat_auto["prediction"],
    "profil": resultat_auto["profil"],
    "intention": resultat_auto["intention"],
    "score": resultat_auto["score"],
})

def simulateur(request):
    resultat = None

    if not request.session.session_key:
        request.session.create()

    session_id = request.session.session_key

    session_visiteur, created = SessionVisiteur.objects.get_or_create(
        session_id=session_id
    )

    if request.method == "POST":
        page_visitee = request.POST.get("page_visitee")
        temps = request.POST.get("temps")
        clics = request.POST.get("clics")

        resultat = analyser_besoin(page_visitee, temps, clics)

        EvenementUtilisateur.objects.create(
            session=session_visiteur,
            type_evenement="formulaire",
            page=page_visitee,
            valeur=f"Temps : {temps} | Clics : {clics}"
        )

        PredictionBesoin.objects.create(
            session=session_visiteur,
            profil=resultat["profil"],
            besoin_probable=resultat["prediction"],
            intention=resultat["intention"],
            score=resultat["score"],
            recommandation=resultat["recommandation"]
        )

    return render(request, "predictor/simulateur.html", resultat or {})

def connexion(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    erreur = None

    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")

        user = authenticate(
            request,
            username=username,
            password=password
        )

        if user is not None:
            login(request, user)
            return redirect("dashboard")
        else:
            erreur = "Nom d'utilisateur ou mot de passe incorrect."

    return render(request, "predictor/connexion.html", {
        "erreur": erreur
    })


def deconnexion(request):
    logout(request)
    return redirect("accueil")

def inscription(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    erreur = None
    User = get_user_model()

    if request.method == "POST":
        username = request.POST.get("username")
        email = request.POST.get("email")
        password = request.POST.get("password")
        nom_entreprise = request.POST.get("nom_entreprise")
        secteur_activite = request.POST.get("secteur_activite")
        nom_site = request.POST.get("nom_site")
        domaine = request.POST.get("domaine")

        if User.objects.filter(username=username).exists():
            erreur = "Ce nom d'utilisateur existe déjà."

        elif User.objects.filter(email=email).exists():
            erreur = "Cette adresse email est déjà utilisée."

        else:
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password
            )

            client = ClientProfessionnel.objects.create(
                utilisateur=user,
                nom_entreprise=nom_entreprise,
                secteur_activite=secteur_activite
            )

            SiteClient.objects.create(
                client=client,
                nom_site=nom_site,
                domaine=domaine
            )

            login(request, user)
            return redirect("dashboard")

    return render(request, "predictor/inscription.html", {
        "erreur": erreur
    })

@csrf_exempt
def capture_lead(request):
    if request.method != "POST":
        return JsonResponse(
            {"success": False, "error": "Méthode non autorisée"},
            status=405
        )

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse(
            {"success": False, "error": "Données JSON invalides"},
            status=400
        )

    api_key = data.get("api_key")
    session_id = data.get("session_id")
    nom = data.get("nom", "")
    email = data.get("email", "")
    telephone = data.get("telephone", "")
    message = data.get("message", "")
    page = data.get("page", "")

    consentement = data.get("consentement")

    if not api_key:
        return JsonResponse(
            {"success": False, "error": "Clé API manquante"},
            status=400
        )

    if not session_id:
        return JsonResponse(
            {"success": False, "error": "Session visiteur manquante"},
            status=400
        )

    if not email and not telephone:
        return JsonResponse(
            {"success": False, "error": "Email ou téléphone obligatoire"},
            status=400
        )

    if consentement not in [True, "true", "1", 1, "on"]:
        return JsonResponse(
            {"success": False, "error": "Consentement obligatoire"},
            status=400
        )

    try:
        site = SiteClient.objects.get(cle_api=api_key, actif=True)
    except SiteClient.DoesNotExist:
        return JsonResponse(
            {"success": False, "error": "Clé API invalide"},
            status=403
        )

    session_visiteur, created = SessionVisiteur.objects.get_or_create(
        site=site,
        session_id=session_id
    )

    resultat_auto = analyser_session_automatique(session_visiteur)

    lead = LeadCapture.objects.create(
        site=site,
        session=session_visiteur,
        nom=nom,
        email=email,
        telephone=telephone,
        message=message,
        profil=resultat_auto["profil"],
        intention=resultat_auto["intention"],
        score=resultat_auto["score"],
        consentement=True
    )

    EvenementUtilisateur.objects.create(
        session=session_visiteur,
        type_evenement="lead",
        page=page,
        valeur=f"Contact laissé : {email or telephone}"
    )

    return JsonResponse({
        "success": True,
        "message": "Contact enregistré",
        "lead_id": lead.id,
        "profil": lead.profil,
        "intention": lead.intention,
        "score": lead.score,
    })