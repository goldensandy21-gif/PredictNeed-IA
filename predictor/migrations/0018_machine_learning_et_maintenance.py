
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("predictor", "0017_securite_comptes_multisite"),
    ]

    operations = [
        migrations.AddField(
            model_name="predictionbesoin",
            name="moteur",
            field=models.CharField(
                choices=[
                    ("regles", "Règles de scoring"),
                    ("machine_learning", "Machine learning"),
                ],
                default="regles",
                max_length=30,
            ),
        ),
        migrations.AddField(
            model_name="predictionbesoin",
            name="probabilite_conversion",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="predictionbesoin",
            name="version_modele",
            field=models.CharField(blank=True, default="", max_length=80),
        ),
        migrations.CreateModel(
            name="JournalMaintenance",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "type_operation",
                    models.CharField(
                        choices=[
                            ("maintenance_quotidienne", "Maintenance quotidienne"),
                            ("purge_rgpd", "Purge RGPD"),
                            ("entrainement_ml", "Entraînement machine learning"),
                            ("securite", "Nettoyage sécurité"),
                            ("essais", "Gestion des essais"),
                        ],
                        max_length=40,
                    ),
                ),
                (
                    "statut",
                    models.CharField(
                        choices=[
                            ("en_cours", "En cours"),
                            ("succes", "Succès"),
                            ("erreur", "Erreur"),
                        ],
                        default="en_cours",
                        max_length=20,
                    ),
                ),
                ("details", models.JSONField(blank=True, default=dict)),
                ("message_erreur", models.TextField(blank=True, default="")),
                ("date_debut", models.DateTimeField(auto_now_add=True)),
                ("date_fin", models.DateTimeField(blank=True, null=True)),
            ],
            options={
                "ordering": ["-date_debut"],
                "indexes": [
                    models.Index(
                        fields=["type_operation", "-date_debut"],
                        name="maintenance_type_date_idx",
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="ModeleMachineLearning",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("version", models.CharField(max_length=80)),
                ("actif", models.BooleanField(default=False)),
                ("noms_caracteristiques", models.JSONField(default=list)),
                ("coefficients", models.JSONField(default=list)),
                ("moyennes_caracteristiques", models.JSONField(default=list)),
                ("echelles_caracteristiques", models.JSONField(default=list)),
                ("intercept", models.FloatField(default=0.0)),
                ("seuil_intention_forte", models.FloatField(default=0.7)),
                ("metriques", models.JSONField(blank=True, default=dict)),
                ("nombre_echantillons", models.PositiveIntegerField(default=0)),
                ("nombre_positifs", models.PositiveIntegerField(default=0)),
                ("nombre_negatifs", models.PositiveIntegerField(default=0)),
                ("date_entrainement", models.DateTimeField(auto_now_add=True)),
                (
                    "site",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="modeles_machine_learning",
                        to="predictor.siteclient",
                    ),
                ),
            ],
            options={
                "ordering": ["-date_entrainement"],
                "indexes": [
                    models.Index(
                        fields=["site", "actif", "-date_entrainement"],
                        name="modele_ml_site_actif_idx",
                    )
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("site", "version"),
                        name="modele_ml_version_unique_par_site",
                    ),
                    models.UniqueConstraint(
                        condition=models.Q(("actif", True)),
                        fields=("site",),
                        name="modele_ml_actif_unique_par_site",
                    ),
                ],
            },
        ),
    ]
