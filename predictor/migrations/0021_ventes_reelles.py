from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("predictor", "0020_attribution_campagnes"),
    ]

    operations = [
        migrations.CreateModel(
            name="Vente",
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
                    "montant",
                    models.DecimalField(
                        decimal_places=2,
                        max_digits=12,
                    ),
                ),
                (
                    "devise",
                    models.CharField(
                        default="EUR",
                        max_length=3,
                    ),
                ),
                (
                    "date_vente",
                    models.DateField(
                        blank=True,
                        null=True,
                    ),
                ),
                (
                    "reference_vente",
                    models.CharField(
                        blank=True,
                        max_length=120,
                        null=True,
                    ),
                ),
                (
                    "statut",
                    models.CharField(
                        choices=[
                            ("confirmee", "Confirmée"),
                            ("annulee", "Annulée"),
                            ("remboursee", "Remboursée"),
                        ],
                        default="confirmee",
                        max_length=20,
                    ),
                ),
                (
                    "source_attribution",
                    models.CharField(
                        blank=True,
                        max_length=100,
                        null=True,
                    ),
                ),
                (
                    "utm_source_attribution",
                    models.CharField(
                        blank=True,
                        max_length=150,
                        null=True,
                    ),
                ),
                (
                    "utm_medium_attribution",
                    models.CharField(
                        blank=True,
                        max_length=150,
                        null=True,
                    ),
                ),
                (
                    "utm_campaign_attribution",
                    models.CharField(
                        blank=True,
                        max_length=150,
                        null=True,
                    ),
                ),
                (
                    "details_attribution",
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
                    "lead",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="ventes",
                        to="predictor.leadcapture",
                    ),
                ),
                (
                    "opportunite",
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="vente",
                        to="predictor.opportunitecrm",
                    ),
                ),
                (
                    "session",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="ventes",
                        to="predictor.sessionvisiteur",
                    ),
                ),
                (
                    "site",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="ventes",
                        to="predictor.siteclient",
                    ),
                ),
            ],
            options={
                "ordering": ["-date_vente", "-date_creation"],
                "indexes": [
                    models.Index(
                        fields=["site", "statut", "-date_vente"],
                        name="vente_site_statut_date_idx",
                    ),
                    models.Index(
                        fields=["site", "utm_campaign_attribution"],
                        name="vente_site_campaign_idx",
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        condition=(
                            models.Q(reference_vente__isnull=False)
                            & ~models.Q(reference_vente="")
                        ),
                        fields=("site", "reference_vente"),
                        name="vente_reference_unique_par_site",
                    ),
                ],
            },
        ),
    ]
