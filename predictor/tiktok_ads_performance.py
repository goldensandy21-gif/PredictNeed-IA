from .ad_performance_regie_core import calculer_performance_regie


def calculer_performance_tiktok_ads(
    campagne,
    *,
    date_debut=None,
    date_fin=None,
):
    return calculer_performance_regie(
        campagne,
        plateforme_attendue="tiktok_ads",
        label_regie="TikTok Ads",
        date_debut=date_debut,
        date_fin=date_fin,
    )
