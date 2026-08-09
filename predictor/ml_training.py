
import math
import random
import uuid
from dataclasses import dataclass
from datetime import datetime

from django.db import transaction
from django.db.models import Prefetch, Q
from django.utils import timezone

from .ml import FEATURE_NAMES, vecteur_caracteristiques
from .models import (
    EvenementUtilisateur,
    LeadCapture,
    ModeleMachineLearning,
)


@dataclass
class TrainingResult:
    site_id: int
    status: str
    message: str
    model_id: int | None = None
    active: bool = False
    samples: int = 0
    positives: int = 0
    negatives: int = 0
    metrics: dict | None = None


def _sigmoid(value):
    value = max(min(float(value), 40.0), -40.0)
    return 1.0 / (1.0 + math.exp(-value))


def _fit_scaler(matrix):
    columns = len(matrix[0])
    means = []
    scales = []
    for index in range(columns):
        values = [row[index] for row in matrix]
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / len(values)
        scale = math.sqrt(variance)
        means.append(float(mean))
        scales.append(float(scale if scale > 1e-12 else 1.0))
    return means, scales


def _transform(matrix, means, scales):
    return [
        [
            (float(value) - means[index]) / scales[index]
            for index, value in enumerate(row)
        ]
        for row in matrix
    ]


def _fit_logistic_regression(
    matrix,
    labels,
    *,
    iterations=1400,
    learning_rate=0.06,
    l2_penalty=0.01,
):
    features = len(matrix[0])
    weights = [0.0] * features
    bias = 0.0
    sample_count = float(len(matrix))

    for _ in range(iterations):
        gradient_weights = [0.0] * features
        gradient_bias = 0.0

        for row, label in zip(matrix, labels):
            linear = bias + sum(
                weight * value
                for weight, value in zip(weights, row)
            )
            error = _sigmoid(linear) - float(label)
            gradient_bias += error
            for index, value in enumerate(row):
                gradient_weights[index] += error * value

        gradient_bias /= sample_count
        for index in range(features):
            gradient_weights[index] = (
                gradient_weights[index] / sample_count
                + l2_penalty * weights[index]
            )
            weights[index] -= learning_rate * gradient_weights[index]
        bias -= learning_rate * gradient_bias

    return weights, bias


def _probabilities(matrix, weights, bias):
    return [
        _sigmoid(
            bias
            + sum(
                weight * value
                for weight, value in zip(weights, row)
            )
        )
        for row in matrix
    ]


def _metrics(labels, probabilities):
    predictions = [1 if probability >= 0.5 else 0 for probability in probabilities]
    true_positive = sum(
        1
        for label, prediction in zip(labels, predictions)
        if label == 1 and prediction == 1
    )
    true_negative = sum(
        1
        for label, prediction in zip(labels, predictions)
        if label == 0 and prediction == 0
    )
    false_positive = sum(
        1
        for label, prediction in zip(labels, predictions)
        if label == 0 and prediction == 1
    )
    false_negative = sum(
        1
        for label, prediction in zip(labels, predictions)
        if label == 1 and prediction == 0
    )

    total = max(len(labels), 1)
    accuracy = (true_positive + true_negative) / total
    precision = (
        true_positive / (true_positive + false_positive)
        if true_positive + false_positive
        else 0.0
    )
    recall = (
        true_positive / (true_positive + false_negative)
        if true_positive + false_negative
        else 0.0
    )
    specificity = (
        true_negative / (true_negative + false_positive)
        if true_negative + false_positive
        else 0.0
    )
    balanced_accuracy = (recall + specificity) / 2.0
    brier = sum(
        (probability - label) ** 2
        for label, probability in zip(labels, probabilities)
    ) / total

    return {
        "accuracy": round(float(accuracy), 6),
        "precision": round(float(precision), 6),
        "recall": round(float(recall), 6),
        "specificity": round(float(specificity), 6),
        "balanced_accuracy": round(float(balanced_accuracy), 6),
        "brier_score": round(float(brier), 6),
        "evaluation_samples": len(labels),
        "true_positive": true_positive,
        "true_negative": true_negative,
        "false_positive": false_positive,
        "false_negative": false_negative,
    }


def _resolved_label(lead):
    opportunities = list(lead.opportunites.all())
    if any(item.etape == "gagne" for item in opportunities):
        return 1
    if any(item.etape == "perdu" for item in opportunities):
        return 0
    if lead.statut_suivi == "converti":
        return 1
    if lead.statut_suivi == "perdu":
        return 0
    return None


def _resolved_leads_for_site(site, *, include_events=False):
    queryset = (
        LeadCapture.objects
        .filter(site=site)
        .filter(
            Q(statut_suivi__in=["converti", "perdu"])
            | Q(opportunites__etape__in=["gagne", "perdu"])
        )
        .select_related("session")
        .prefetch_related("opportunites")
        .distinct()
        .order_by("session_id", "-date_creation")
    )

    if include_events:
        queryset = queryset.prefetch_related(
            Prefetch(
                "session__evenements",
                queryset=EvenementUtilisateur.objects.order_by("date_creation"),
                to_attr="ml_evenements",
            ),
        )

    return queryset


def compter_resultats_resolus(site):
    samples = {}
    for lead in _resolved_leads_for_site(site):
        if lead.session_id in samples:
            continue
        label = _resolved_label(lead)
        if label is None:
            continue
        samples[lead.session_id] = int(label)

    positives = sum(samples.values())
    negatives = len(samples) - positives
    return {
        "total": len(samples),
        "positives": positives,
        "negatives": negatives,
    }


def _dataset_for_site(site):
    leads = _resolved_leads_for_site(site, include_events=True)

    samples = {}
    for lead in leads:
        if lead.session_id in samples:
            continue
        label = _resolved_label(lead)
        if label is None:
            continue
        samples[lead.session_id] = (lead.session, label)

    matrix = []
    labels = []
    session_ids = []
    for session_id, (session, label) in samples.items():
        matrix.append(vecteur_caracteristiques(session))
        labels.append(int(label))
        session_ids.append(session_id)
    return matrix, labels, session_ids


def _stratified_split(matrix, labels, *, seed):
    positive_indices = [
        index for index, label in enumerate(labels) if label == 1
    ]
    negative_indices = [
        index for index, label in enumerate(labels) if label == 0
    ]

    rng = random.Random(seed)
    rng.shuffle(positive_indices)
    rng.shuffle(negative_indices)

    def split_class(indices):
        test_size = max(1, round(len(indices) * 0.20))
        test_size = min(test_size, len(indices) - 1)
        return indices[test_size:], indices[:test_size]

    positive_train, positive_test = split_class(positive_indices)
    negative_train, negative_test = split_class(negative_indices)

    train_indices = positive_train + negative_train
    test_indices = positive_test + negative_test
    rng.shuffle(train_indices)
    rng.shuffle(test_indices)

    train_matrix = [matrix[index] for index in train_indices]
    train_labels = [labels[index] for index in train_indices]
    test_matrix = [matrix[index] for index in test_indices]
    test_labels = [labels[index] for index in test_indices]
    return train_matrix, train_labels, test_matrix, test_labels


def entrainer_site(
    site,
    *,
    minimum_samples,
    minimum_per_class,
    minimum_balanced_accuracy,
    activate_low_quality=False,
):
    matrix, labels, _ = _dataset_for_site(site)
    positives = sum(labels)
    negatives = len(labels) - positives

    if (
        len(labels) < minimum_samples
        or positives < minimum_per_class
        or negatives < minimum_per_class
    ):
        return TrainingResult(
            site_id=site.pk,
            status="insufficient_data",
            message=(
                f"{len(labels)} session(s) résolue(s), "
                f"{positives} positive(s), {negatives} négative(s). "
                f"Minimum requis : {minimum_samples} au total et "
                f"{minimum_per_class} par classe."
            ),
            samples=len(labels),
            positives=positives,
            negatives=negatives,
        )

    train_matrix, train_labels, test_matrix, test_labels = _stratified_split(
        matrix,
        labels,
        seed=site.pk * 1009 + 20260806,
    )
    means, scales = _fit_scaler(train_matrix)
    train_scaled = _transform(train_matrix, means, scales)
    test_scaled = _transform(test_matrix, means, scales)

    evaluation_weights, evaluation_bias = _fit_logistic_regression(
        train_scaled,
        train_labels,
    )
    evaluation_probabilities = _probabilities(
        test_scaled,
        evaluation_weights,
        evaluation_bias,
    )
    metrics = _metrics(test_labels, evaluation_probabilities)
    quality_ok = (
        metrics["balanced_accuracy"] >= minimum_balanced_accuracy
        and metrics["recall"] >= 0.40
        and metrics["specificity"] >= 0.40
    )

    all_means, all_scales = _fit_scaler(matrix)
    all_scaled = _transform(matrix, all_means, all_scales)
    final_weights, final_bias = _fit_logistic_regression(
        all_scaled,
        labels,
    )

    version = (
        timezone.now().strftime("ml-%Y%m%d-%H%M%S")
        + "-"
        + uuid.uuid4().hex[:8]
    )
    activate = quality_ok or activate_low_quality

    with transaction.atomic():
        model = ModeleMachineLearning.objects.create(
            site=site,
            version=version,
            actif=False,
            noms_caracteristiques=FEATURE_NAMES,
            coefficients=[float(value) for value in final_weights],
            moyennes_caracteristiques=[float(value) for value in all_means],
            echelles_caracteristiques=[float(value) for value in all_scales],
            intercept=float(final_bias),
            seuil_intention_forte=0.70,
            metriques={
                **metrics,
                "quality_threshold": minimum_balanced_accuracy,
                "quality_ok": quality_ok,
                "trained_at": datetime.now().isoformat(),
            },
            nombre_echantillons=len(labels),
            nombre_positifs=positives,
            nombre_negatifs=negatives,
        )

        if activate:
            ModeleMachineLearning.objects.filter(
                site=site,
                actif=True,
            ).exclude(pk=model.pk).update(actif=False)
            model.actif = True
            model.save(update_fields=["actif"])

    return TrainingResult(
        site_id=site.pk,
        status="trained",
        message=(
            f"Modèle {model.version} entraîné sur {len(labels)} sessions. "
            f"Balanced accuracy : {metrics['balanced_accuracy']:.3f}. "
            f"Actif : {model.actif}."
        ),
        model_id=model.pk,
        active=model.actif,
        samples=len(labels),
        positives=positives,
        negatives=negatives,
        metrics=metrics,
    )
