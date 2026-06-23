from django.urls import path
from . import views

urlpatterns = [
    path('', views.accueil, name='accueil'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('dashboard/nettoyer-evenements/', views.nettoyer_evenements, name='nettoyer_evenements'),
    path(
    'leads/<int:lead_id>/statut/<str:nouveau_statut>/',
    views.changer_statut_lead,
    name='changer_statut_lead'
),
    path('sites/ajouter/', views.ajouter_site, name='ajouter_site'),
    path('simulateur/', views.simulateur, name='simulateur'),
    path('connexion/', views.connexion, name='connexion'),
    path('inscription/', views.inscription, name='inscription'),
    path('deconnexion/', views.deconnexion, name='deconnexion'),
    path('api/track/', views.track_event, name='track_event'),
    path('api/lead/', views.capture_lead, name='capture_lead'),
]