"""Train only on real imported histories; persist safe numeric coefficients."""

import math
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, brier_score_loss, log_loss


class Predictor:
    def __init__(self, artifact):
        self.artifact = artifact

    def predict_proba(self, rows):
        result = []
        for row in rows:
            z = self.artifact["intercept"] + sum(
                a * b for a, b in zip(row, self.artifact["coefficients"])
            )
            p = 1 / (1 + math.exp(-max(-500, min(500, z))))
            result.append([1 - p, p])
        return result


def train(examples):
    examples = sorted(examples, key=lambda e: e["start"])
    if len(examples) < 50:
        raise ValueError("Import at least 50 completed real attempts before training.")
    cutoff = examples[int(len(examples) * 0.8)]["start"]
    validation_cutoff = examples[int(len(examples) * 0.6)]["start"]
    # Purge overlapping outcome windows at the chronological boundary.
    training = [e for e in examples if e["end"] < cutoff]
    test = [e for e in examples if e["start"] >= cutoff]
    fitting = [e for e in examples if e["end"] < validation_cutoff]
    validation = [
        e for e in examples if validation_cutoff <= e["start"] and e["end"] < cutoff
    ]
    if (
        len(training) < 20
        or len(test) < 10
        or len({e["outcome"] for e in training}) < 2
    ):
        raise ValueError(
            "Need more time-separated attempts and both successful and unsuccessful training examples."
        )
    if len(fitting) < 10 or not validation or len({e["outcome"] for e in fitting}) < 2:
        raise ValueError(
            "Need both classes and enough attempts in the early training and validation windows."
        )
    search = []
    for c in [0.01, 0.1, 1.0, 10.0, 100.0]:
        candidate = LogisticRegression(C=c, random_state=0, max_iter=1000)
        candidate.fit([e["features"] for e in fitting], [e["outcome"] for e in fitting])
        estimates = candidate.predict_proba([e["features"] for e in validation])[:, 1]
        search.append(
            {
                "C": c,
                "validation_brier": float(
                    brier_score_loss([e["outcome"] for e in validation], estimates)
                ),
            }
        )
    best = min(search, key=lambda row: row["validation_brier"])
    model = LogisticRegression(C=best["C"], random_state=0, max_iter=1000)
    model.fit([e["features"] for e in training], [e["outcome"] for e in training])
    y = [e["outcome"] for e in test]
    pred = model.predict_proba([e["features"] for e in test])[:, 1]
    bins = []
    for i in range(5):
        pairs = [
            (float(p), target) for p, target in zip(pred, y) if i / 5 <= p < (i + 1) / 5
        ]
        if pairs:
            bins.append(
                {
                    "count": len(pairs),
                    "predicted": sum(p for p, _ in pairs) / len(pairs),
                    "observed": sum(t for _, t in pairs) / len(pairs),
                }
            )
    base_rate = sum(e["outcome"] for e in training) / len(training)
    band = [(float(p), target) for p, target in zip(pred, y) if 0.5 <= p <= 0.7]
    metrics = {
        "training_attempts": len(training),
        "test_attempts": len(test),
        "cutoff": cutoff,
        "accuracy": float(accuracy_score(y, pred >= 0.5)),
        "brier": float(brier_score_loss(y, pred)),
        "log_loss": float(log_loss(y, pred, labels=[0, 1])),
        "elo_brier": float(brier_score_loss(y, [e["probability"] for e in test])),
        "base_rate_brier": float(brier_score_loss(y, [base_rate] * len(y))),
        "majority_accuracy": float(accuracy_score(y, [int(base_rate >= 0.5)] * len(y))),
        "calibration": bins,
        "validation_attempts": len(validation),
        "validation_cutoff": validation_cutoff,
        "hyperparameter_search": search,
        "selected_C": best["C"],
        "test_success_rate": sum(y) / len(y),
        "recommendation_band": {
            "count": len(band),
            "mean_predicted": sum(p for p, _ in band) / len(band) if band else None,
            "observed_success": sum(t for _, t in band) / len(band) if band else None,
        },
    }
    # Publish the evaluated model, not an unevaluated fit on future examples.
    return {
        "coefficients": model.coef_[0].tolist(),
        "intercept": float(model.intercept_[0]),
        "metrics": metrics,
        "version": 2,
    }
