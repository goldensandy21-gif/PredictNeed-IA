from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from .models import AutomatisationEmail, EmailAutomatise, EtapeAutomatisationEmail, LeadCapture


DEFAULT_LEAD_SUBJECT = "Votre demande a bien été enregistrée"
DEFAULT_LEAD_BODY = (
    "Bonjour {nom},\n\n"
    "Votre demande a bien été enregistrée par {entreprise}. "
    "Nous reviendrons vers vous rapidement.\n\n"
    "Message reçu : {message}\n\n"
    "À bientôt,\n"
    "{entreprise}"
)

DEFAULT_AUTOMATION_STEPS = [
    {
        "ordre": 1,
        "nom": "Confirmation immédiate",
        "delai_jours": 0,
        "sujet": DEFAULT_LEAD_SUBJECT,
        "contenu": DEFAULT_LEAD_BODY,
    },
    {
        "ordre": 2,
        "nom": "Relance douce",
        "delai_jours": 2,
        "sujet": "Souhaitez-vous compléter votre demande ?",
        "contenu": (
            "Bonjour {nom},\n\n"
            "Nous revenons vers vous au sujet de votre demande transmise à {entreprise}. "
            "Si votre besoin est toujours d'actualité, vous pouvez répondre directement à ce message "
            "avec vos disponibilités ou les précisions utiles.\n\n"
            "À bientôt,\n"
            "{entreprise}"
        ),
    },
    {
        "ordre": 3,
        "nom": "Relance valeur",
        "delai_jours": 5,
        "sujet": "Votre projet est-il toujours d'actualité ?",
        "contenu": (
            "Bonjour {nom},\n\n"
            "Votre demande semble liée à : {profil}. "
            "Pour vous aider à avancer, l'étape la plus utile est souvent de clarifier le besoin, "
            "le délai et le résultat attendu.\n\n"
            "Vous pouvez répondre à ce message pour nous dire où vous en êtes.\n\n"
            "{entreprise}"
        ),
    },
    {
        "ordre": 4,
        "nom": "Dernière relance",
        "delai_jours": 10,
        "sujet": "Dernière relance concernant votre demande",
        "contenu": (
            "Bonjour {nom},\n\n"
            "Nous n'avons pas encore eu de retour concernant votre demande. "
            "Si elle est toujours d'actualité, vous pouvez répondre à cet email. "
            "Dans le cas contraire, aucune action n'est nécessaire.\n\n"
            "Bien cordialement,\n"
            "{entreprise}"
        ),
    },
]


def get_or_create_lead_confirmation_automation(site):
    automatisation = (
        AutomatisationEmail.objects
        .filter(
            client=site.client,
            site=site,
            type_declencheur="lead_confirmation",
        )
        .order_by("-date_mise_a_jour")
        .first()
    )

    if automatisation:
        ensure_default_automation_steps(automatisation)
        return automatisation

    automatisation = AutomatisationEmail.objects.create(
        client=site.client,
        site=site,
        nom="Confirmation automatique de demande",
        type_declencheur="lead_confirmation",
        sujet=DEFAULT_LEAD_SUBJECT,
        contenu=DEFAULT_LEAD_BODY,
        actif=True,
        envoyer_copie_interne=False,
        email_copie=settings.PREDICTNEED_CONTACT_EMAIL or site.client.utilisateur.email,
    )
    ensure_default_automation_steps(automatisation)
    return automatisation


def ensure_default_automation_steps(automatisation):
    for step in DEFAULT_AUTOMATION_STEPS:
        EtapeAutomatisationEmail.objects.get_or_create(
            automatisation=automatisation,
            ordre=step["ordre"],
            defaults={
                "nom": step["nom"],
                "delai_jours": step["delai_jours"],
                "sujet": step["sujet"],
                "contenu": step["contenu"],
                "actif": True,
                "stopper_si_lead_traite": True,
            },
        )


def render_automation_text(template, lead):
    replacements = {
        "nom": lead.nom or "Madame, Monsieur",
        "email": lead.email or "",
        "telephone": lead.telephone or "",
        "message": lead.message or "Votre demande de contact",
        "site": lead.site.nom_site,
        "domaine": lead.site.domaine,
        "entreprise": lead.site.client.nom_entreprise,
        "profil": lead.profil or "",
        "intention": lead.intention or "",
        "score": str(lead.score or 0),
    }

    rendered = template

    for key, value in replacements.items():
        rendered = rendered.replace("{" + key + "}", value)

    return rendered


def lead_est_traite(lead):
    return lead.statut_suivi in {"contacte", "converti", "perdu"}


def envoyer_etape_automation(lead, automatisation, etape, date_programmee=None):
    if not lead.email:
        EmailAutomatise.objects.create(
            automatisation=automatisation,
            etape=etape,
            site=lead.site,
            lead=lead,
            destinataire=None,
            sujet=etape.sujet,
            message="Aucun email renseigné pour ce lead.",
            numero_etape=etape.ordre,
            date_programmee=date_programmee,
            statut="ignore",
        )
        return None

    if not automatisation.actif:
        EmailAutomatise.objects.create(
            automatisation=automatisation,
            etape=etape,
            site=lead.site,
            lead=lead,
            destinataire=lead.email,
            sujet=etape.sujet,
            message="Automatisation désactivée.",
            numero_etape=etape.ordre,
            date_programmee=date_programmee,
            statut="ignore",
        )
        return None

    if etape.stopper_si_lead_traite and lead_est_traite(lead):
        EmailAutomatise.objects.create(
            automatisation=automatisation,
            etape=etape,
            site=lead.site,
            lead=lead,
            destinataire=lead.email,
            sujet=etape.sujet,
            message="Lead déjà traité, relance non envoyée.",
            numero_etape=etape.ordre,
            date_programmee=date_programmee,
            statut="ignore",
        )
        return None

    sujet = render_automation_text(etape.sujet, lead)
    message = render_automation_text(etape.contenu, lead)
    destinataires = [lead.email]

    if automatisation.envoyer_copie_interne and automatisation.email_copie:
        destinataires.append(automatisation.email_copie)

    try:
        send_mail(
            sujet,
            message,
            settings.DEFAULT_FROM_EMAIL,
            destinataires,
            fail_silently=False,
        )
    except Exception as exc:
        EmailAutomatise.objects.create(
            automatisation=automatisation,
            etape=etape,
            site=lead.site,
            lead=lead,
            destinataire=lead.email,
            sujet=sujet,
            message=message,
            numero_etape=etape.ordre,
            date_programmee=date_programmee,
            date_envoi=timezone.now(),
            statut="erreur",
            erreur=str(exc),
        )
        return None

    return EmailAutomatise.objects.create(
        automatisation=automatisation,
        etape=etape,
        site=lead.site,
        lead=lead,
        destinataire=lead.email,
        sujet=sujet,
        message=message,
        numero_etape=etape.ordre,
        date_programmee=date_programmee,
        date_envoi=timezone.now(),
        statut="envoye",
    )


def envoyer_confirmation_lead(lead):
    automatisation = get_or_create_lead_confirmation_automation(lead.site)
    premiere_etape = automatisation.etapes.filter(actif=True).order_by("ordre").first()

    if not premiere_etape:
        ensure_default_automation_steps(automatisation)
        premiere_etape = automatisation.etapes.filter(actif=True).order_by("ordre").first()

    if premiere_etape is None:
        return None

    return envoyer_etape_automation(
        lead,
        automatisation,
        premiere_etape,
        date_programmee=lead.date_creation,
    )


def envoyer_relances_dues(now=None):
    now = now or timezone.now()
    total_envoyes = 0
    total_ignores = 0

    automatisations = (
        AutomatisationEmail.objects
        .filter(actif=True)
        .prefetch_related("etapes")
        .select_related("site", "client")
    )

    for automatisation in automatisations:
        if automatisation.site:
            leads = LeadCapture.objects.filter(site=automatisation.site)
        else:
            leads = LeadCapture.objects.filter(site__client=automatisation.client)

        for etape in automatisation.etapes.filter(actif=True).order_by("ordre"):
            date_limite = now - timedelta(days=etape.delai_jours)
            leads_dues = leads.filter(date_creation__lte=date_limite)

            for lead in leads_dues:
                deja_traite = EmailAutomatise.objects.filter(
                    automatisation=automatisation,
                    lead=lead,
                    numero_etape=etape.ordre,
                ).exists()

                if deja_traite:
                    continue

                email = envoyer_etape_automation(
                    lead,
                    automatisation,
                    etape,
                    date_programmee=lead.date_creation + timedelta(days=etape.delai_jours),
                )

                if email and email.statut == "envoye":
                    total_envoyes += 1
                else:
                    total_ignores += 1

    return {
        "envoyes": total_envoyes,
        "ignores": total_ignores,
    }
