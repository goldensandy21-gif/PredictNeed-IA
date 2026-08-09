from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path('', views.accueil, name='accueil'),
    path('robots.txt', views.robots_txt, name='robots_txt'),
    path('sitemap.xml', views.sitemap_xml, name='sitemap_xml'),
    path('healthz/', views.health_check, name='health_check'),
    path('a-propos/', views.a_propos, name='a_propos'),
    path('contact/', views.contact, name='contact'),
    path('newsletter/inscription/', views.newsletter_inscription, name='newsletter_inscription'),
    path('newsletter/confirmer/<uuid:token>/', views.newsletter_confirmer, name='newsletter_confirmer'),
    path('newsletter/desinscription/<uuid:token>/', views.newsletter_desinscription, name='newsletter_desinscription'),
    path(
        'compte/confirmer-email/<str:token>/',
        views.confirmer_email_compte,
        name='confirmer_email_compte',
    ),
    path(
        'compte/renvoyer-confirmation-email/',
        views.renvoyer_confirmation_email,
        name='renvoyer_confirmation_email',
    ),
    path(
        'mot-de-passe-oublie/',
        auth_views.PasswordResetView.as_view(
            template_name='registration/password_reset_form.html',
            email_template_name='registration/password_reset_email.txt',
            subject_template_name='registration/password_reset_subject.txt',
        ),
        name='password_reset',
    ),
    path(
        'mot-de-passe-oublie/envoye/',
        auth_views.PasswordResetDoneView.as_view(
            template_name='registration/password_reset_done.html',
        ),
        name='password_reset_done',
    ),
    path(
        'reinitialiser-mot-de-passe/<uidb64>/<token>/',
        auth_views.PasswordResetConfirmView.as_view(
            template_name='registration/password_reset_confirm.html',
        ),
        name='password_reset_confirm',
    ),
    path(
        'reinitialiser-mot-de-passe/termine/',
        auth_views.PasswordResetCompleteView.as_view(
            template_name='registration/password_reset_complete.html',
        ),
        name='password_reset_complete',
    ),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('dashboard/parametres/', views.dashboard_parametres, name='dashboard_parametres'),
    path('dashboard/nettoyer-evenements/', views.nettoyer_evenements, name='nettoyer_evenements'),

    # Pages professionnelles des modules
    path("dashboard/prediction-avancee/", views.module_prediction_avancee, name="module_prediction_avancee"),
    path("dashboard/segmentation/", views.module_segmentation, name="module_segmentation"),
    path("dashboard/ecommerce/", views.module_ecommerce, name="module_ecommerce"),
    path("dashboard/visualisations/", views.module_visualisations, name="module_visualisations"),
    path("dashboard/historique/", views.module_historique, name="module_historique"),
    path("dashboard/multicanal/", views.module_multicanal, name="module_multicanal"),
    path("dashboard/connecteurs/", views.module_connecteurs, name="module_connecteurs"),
    path("dashboard/publicite/", views.module_publicite, name="module_publicite"),
    path("dashboard/securite/", views.module_securite, name="module_securite"),
    path(
        "connecteurs/<str:plateforme>/connecter/",
        views.demarrer_oauth_connecteur,
        name="demarrer_oauth_connecteur"
    ),
    path(
        "connecteurs/<str:plateforme>/callback/",
        views.connecteur_oauth_callback,
        name="connecteur_oauth_callback"
    ),
    path(
        "connecteurs/google-ads/selectionner-compte/",
        views.selectionner_compte_google_ads,
        name="selectionner_compte_google_ads"
    ),
    path(
        "connecteurs/<int:compte_id>/synchroniser/",
        views.synchroniser_compte_connecteur,
        name="synchroniser_compte_connecteur"
    ),
    path(
        "connecteurs/<int:compte_id>/deconnecter/",
        views.deconnecter_compte_connecteur,
        name="deconnecter_compte_connecteur"
    ),
    path(
        "connecteurs/sites/<int:site_id>/retargeting/",
        views.mettre_a_jour_retargeting_site,
        name="mettre_a_jour_retargeting_site"
    ),

    path(
        'leads/<int:lead_id>/statut/<str:nouveau_statut>/',
        views.changer_statut_lead,
        name='changer_statut_lead'
    ),

    path(
        'leads/<int:lead_id>/creer-opportunite/',
        views.creer_opportunite_depuis_lead,
        name='creer_opportunite_depuis_lead'
    ),

    path(
        'opportunites/<int:opportunite_id>/modifier/',
        views.modifier_opportunite,
        name='modifier_opportunite'
    ),
    path(
        'automatisations-email/<int:automatisation_id>/modifier/',
        views.modifier_automatisation_email,
        name='modifier_automatisation_email'
    ),

    path('sites/ajouter/', views.ajouter_site, name='ajouter_site'),
    path('simulateur/', views.simulateur, name='simulateur'),
    path('prix/', views.prix, name='prix'),
    path('fonctionnalites/', views.fonctionnalites, name='fonctionnalites'),
    path('fonctionnalites/<slug:slug>/', views.fonctionnalite_detail, name='fonctionnalite_detail'),
    path('guide-utilisation/', views.guide_utilisation, name='guide_utilisation'),
    path('mentions-legales/', views.mentions_legales, name='mentions_legales'),
    path('politique-de-confidentialite/', views.politique_confidentialite, name='politique_confidentialite'),
    path('conditions-generales-utilisation/', views.conditions_generales_utilisation, name='conditions_generales_utilisation'),
    path('politique-cookies/', views.politique_cookies, name='politique_cookies'),
    path(
        'dashboard/abonnement/activer/',
        views.activer_abonnement,
        name='activer_abonnement',
    ),
    path('paiement/succes/', views.paiement_succes, name='paiement_succes'),
    path('paiement/annule/', views.paiement_annule, name='paiement_annule'),
    path('stripe/webhook/', views.stripe_webhook, name='stripe_webhook'),
    path('connexion/', views.connexion, name='connexion'),
    path('inscription/', views.inscription, name='inscription'),
    path('deconnexion/', views.deconnexion, name='deconnexion'),
    path(
        'api/install/',
        views.tracker_installation_ping,
        name='tracker_installation_ping',
    ),
    path('api/track/', views.track_event, name='track_event'),
    path('api/lead/', views.capture_lead, name='capture_lead'),
]


from django.urls import path as _path
from . import views as _legal_views

urlpatterns += [
    _path(
        "accord-traitement-donnees/",
        _legal_views.accord_traitement_donnees,
        name="accord_traitement_donnees",
    ),
]
