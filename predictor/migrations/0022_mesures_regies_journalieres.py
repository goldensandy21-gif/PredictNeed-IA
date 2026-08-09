from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("predictor", "0021_ventes_reelles"),
    ]

    operations = [
        migrations.AddField(
            model_name="campagneexterne",
            name="source_donnees",
            field=models.CharField(
                choices=[
                    ("utm_predictneed", "UTM PredictNeed"),
                    ("api_regie", "API native de la régie"),
                ],
                default="utm_predictneed",
                max_length=30,
            ),
        ),
        migrations.CreateModel(
            name="MesureCampagneExterne",
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
                    "plateforme",
                    models.CharField(
                        choices=[
                            ("google_ads", "Google Ads"),
                            ("meta_ads", "Meta Ads"),
                            ("linkedin_ads", "LinkedIn Ads"),
                            ("tiktok_ads", "TikTok Ads"),
                        ],
                        max_length=40,
                    ),
                ),
                (
                    "date",
                    models.DateField(),
                ),
                (
                    "impressions",
                    models.PositiveBigIntegerField(default=0),
                ),
                (
                    "clics",
                    models.PositiveBigIntegerField(default=0),
                ),
                (
                    "conversions",
                    models.DecimalField(
                        decimal_places=4,
                        default=0,
                        max_digits=14,
                    ),
                ),
                (
                    "depense",
                    models.DecimalField(
                        decimal_places=2,
                        default=0,
                        max_digits=14,
                    ),
                ),
                (
                    "devise",
                    models.CharField(
                        default="EUR",
                        max_length=12,
                    ),
                ),
                (
                    "donnees_brutes",
                    models.JSONField(
                        blank=True,
                        default=dict,
                    ),
                ),
                (
                    "date_creation",
                    models.DateTimeField(auto_now_add=True),
                ),
                (
                    "date_mise_a_jour",
                    models.DateTimeField(auto_now=True),
                ),
                (
                    "campagne",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="mesures_journalieres",
                        to="predictor.campagneexterne",
                    ),
                ),
                (
                    "compte",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="mesures_campagnes",
                        to="predictor.compteconnecteexterne",
                    ),
                ),
                (
                    "site",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="mesures_campagnes_externes",
                        to="predictor.siteclient",
                    ),
                ),
            ],
            options={
                "ordering": ["-date", "campagne__nom"],
                "indexes": [
                    models.Index(
                        fields=["site", "plateforme", "-date"],
                        name="mesure_site_plat_date_idx",
                    ),
                    models.Index(
                        fields=["compte", "-date"],
                        name="mesure_compte_date_idx",
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("campagne", "date"),
                        name="mesure_campagne_jour_uniq",
                    ),
                ],
            },
        ),
    ]
