
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("predictor", "0015_essai_gratuit_sans_carte")]
    operations = [
        migrations.CreateModel(
            name="NewsletterInscription",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("prenom", models.CharField(blank=True, default="", max_length=100)),
                ("email", models.EmailField(max_length=254, unique=True)),
                ("statut", models.CharField(choices=[("en_attente", "En attente de confirmation"), ("confirmee", "Confirmée"), ("desinscrite", "Désinscrite")], default="en_attente", max_length=20)),
                ("consentement", models.BooleanField(default=False)),
                ("version_confidentialite", models.CharField(blank=True, default="", max_length=30)),
                ("token", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("source", models.CharField(blank=True, default="", max_length=255)),
                ("date_consentement", models.DateTimeField(blank=True, null=True)),
                ("date_confirmation", models.DateTimeField(blank=True, null=True)),
                ("date_desinscription", models.DateTimeField(blank=True, null=True)),
                ("date_creation", models.DateTimeField(auto_now_add=True)),
                ("date_mise_a_jour", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["-date_creation"]},
        ),
    ]
