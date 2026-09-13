"""Risk-controlled coverage: fit the real risk model, choose a calibrated threshold.
BUILD_SPEC.md §7.4, §8. "This is ~40 lines and it is the differentiator. Do not skip it."

Two different human labels, two different jobs:
1. fit_risk_model -- logistic regression on the 7 risk features vs. the `should_escalate`
   label from golden_v1.jsonl's main labelling pass. Replaces verify.py's
   RISK_PLACEHOLDER_WEIGHTS with real, interpretable coefficients.
2. choose_threshold -- Clopper-Pearson upper-bound search on `bad_to_autosend`, a SEPARATE,
   per-system, blind-to-system label collected only after every system has run on the golden
   set (docs/ANNOTATION_GUIDE.md §3). Not yet collected -- main() fails loudly and specifically
   when that file is missing, rather than approximating it from should_escalate.

Runs alone: `python -m cordon.calibrate --help`.
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

import numpy as np
from rich.console import Console
from scipy.stats import beta
from sklearn.linear_model import LogisticRegression

from config import (
    CHOSEN_BRAND, CLOPPER_PEARSON_CONF, CLOPPER_PEARSON_MIN_N, GOLDEN_DIR, GOLDEN_FIT_FRACTION,
    RISK_ALPHAS, RISK_COST_RATIOS, RISK_PLACEHOLDER_WEIGHTS, SEED,
)
from cordon.agent import render_taxonomy, run_agent
from cordon.index import load_index

console = Console()

RISK_FEATURE_NAMES = list(RISK_PLACEHOLDER_WEIGHTS)  # canonical order, one place


def clopper_pearson_upper(k: int, n: int, conf: float = CLOPPER_PEARSON_CONF) -> float:
    """Upper bound on a binomial rate. k failures out of n. BUILD_SPEC.md §8."""
    if n == 0 or k == n:
        return 1.0
    return float(beta.ppf(conf, k + 1, n - k))


def choose_threshold(scores: np.ndarray, is_bad: np.ndarray, alpha: float = 0.05,
                      conf: float = CLOPPER_PEARSON_CONF) -> tuple[float, float]:
    """Largest coverage whose UPPER bound on bad-auto rate is <= alpha. BUILD_SPEC.md §8."""
    best = (0.0, 0.0)
    for tau in sorted(set(scores.tolist())):
        auto = scores <= tau
        n = int(auto.sum())
        if n < CLOPPER_PEARSON_MIN_N:
            continue
        k = int((is_bad & auto).sum())
        if clopper_pearson_upper(k, n, conf) <= alpha:
            coverage = n / len(scores)
            if coverage >= best[1]:
                best = (float(tau), coverage)
    return best


def fit_risk_model(features: np.ndarray, should_escalate: np.ndarray) -> LogisticRegression:
    """BUILD_SPEC.md §7.4: 7 features, ~100 rows. Report the coefficients -- interpretable."""
    return LogisticRegression(random_state=SEED).fit(features, should_escalate)


def coverage_risk_curve(scores: np.ndarray, is_bad: np.ndarray,
                         alphas: list[float] = RISK_ALPHAS) -> list[dict]:
    """BUILD_SPEC.md §8 deliverable: X = risk budget alpha, Y = % volume auto-handled."""
    return [{"alpha": a, **dict(zip(("tau", "coverage"), choose_threshold(scores, is_bad, a)))}
            for a in alphas]


def expected_saving(coverage: float, p_bad: float, cost_ratio: float) -> float:
    """BUILD_SPEC.md §8 business framing. C_h = human cost, C_b = bad-auto cost in units of
    C_h. saving(tau) = coverage(tau) * (1 - p_bad(tau) * (1 + C_b))."""
    return coverage * (1 - p_bad * (1 + cost_ratio))


def split_golden_for_calibration(items: list[dict], seed: int = SEED,
                                  fit_fraction: float = GOLDEN_FIT_FRACTION) -> tuple[list, list]:
    """Stratified split of the golden set itself into a fitting role and a held-out evaluation
    role (docs/DECISION_LOG.md's resolution of §8's calib/test wording)."""
    by_stratum: dict[str, list[dict]] = {}
    for item in items:
        by_stratum.setdefault(item["stratum"], []).append(item)
    fit_items, holdout_items = [], []
    for stratum_items in by_stratum.values():
        shuffled = stratum_items[:]
        random.Random(seed).shuffle(shuffled)
        cut = round(len(shuffled) * fit_fraction)
        fit_items += shuffled[:cut]
        holdout_items += shuffled[cut:]
    return fit_items, holdout_items


def compute_features_and_labels(golden_items: list[dict], index: dict, taxonomy_text: str,
                                 brand: str) -> tuple[np.ndarray, np.ndarray, list[dict]]:
    """Runs the real agent on each item's message to get its risk features. Items where a
    hard override fired (risk_score is None) are excluded -- they're never learned, on either
    side of the placeholder-vs-fitted line (docs/DECISION_LOG.md #35, #41)."""
    features, labels, kept = [], [], []
    for item in golden_items:
        trace = run_agent(item["customer_message"], index, taxonomy_text, brand)
        if trace.risk_score is None:
            continue
        features.append([trace.risk_score.features[name] for name in RISK_FEATURE_NAMES])
        labels.append(bool(item["should_escalate"]))
        kept.append(item)
    return np.array(features), np.array(labels), kept


def main() -> None:
    parser = argparse.ArgumentParser(description="Fit the risk model + choose a calibrated threshold")
    parser.add_argument("--brand", default=CHOSEN_BRAND)
    parser.add_argument("--golden", default=str(GOLDEN_DIR / "golden_v1.jsonl"))
    parser.add_argument("--bad-labels", default=str(GOLDEN_DIR / "bad_to_autosend_v1.jsonl"))
    args = parser.parse_args()

    golden_path = Path(args.golden)
    if not golden_path.exists():
        raise FileNotFoundError(f"{golden_path} not found. Label the golden set first: "
                                 "`make label` (docs/ANNOTATION_GUIDE.md).")
    items = [json.loads(line) for line in open(golden_path)]
    fit_items, holdout_items = split_golden_for_calibration(items)

    index = load_index(args.brand)
    taxonomy_text = render_taxonomy(Path("taxonomy/intents.yaml"))
    features, should_escalate, _ = compute_features_and_labels(fit_items, index, taxonomy_text,
                                                                 args.brand)
    model = fit_risk_model(features, should_escalate)
    console.log("Fitted risk model coefficients:")
    for name, coef in zip(RISK_FEATURE_NAMES, model.coef_[0]):
        console.log(f"  {name}: {coef:.3f}")

    bad_labels_path = Path(args.bad_labels)
    if not bad_labels_path.exists():
        raise FileNotFoundError(
            f"Risk model fit succeeded (it only needs should_escalate). But {bad_labels_path} "
            "is missing -- the threshold search needs a SEPARATE, blind-to-system label "
            "(bad_to_autosend) collected after every system has run on the golden set, per "
            "docs/ANNOTATION_GUIDE.md §3. This is not approximated from should_escalate; "
            "collect it, then rerun."
        )
    # DECISION: bad_to_autosend_v1.jsonl carries rows for all 5 systems (docs/DECISION_LOG.md) --
    # filter to this system's own rows, or item_ids shared across systems silently collide.
    bad_labels = {r["item_id"]: r["bad_to_autosend"] for r in
                  (json.loads(line) for line in open(bad_labels_path)) if r["system"] == "cordon"}
    holdout_features, _, holdout_kept = compute_features_and_labels(holdout_items, index,
                                                                      taxonomy_text, args.brand)
    missing = [i["item_id"] for i in holdout_kept if i["item_id"] not in bad_labels]
    if missing:
        raise KeyError(
            f"{bad_labels_path} exists but is missing cordon's bad_to_autosend label for "
            f"{len(missing)} holdout item(s): {missing[:5]}{'...' if len(missing) > 5 else ''}. "
            "Labelling is incomplete -- finish `python -m cordon.bad_to_autosend_labeler`, "
            "then rerun."
        )
    holdout_scores = model.predict_proba(holdout_features)[:, 1]
    holdout_is_bad = np.array([bad_labels[i["item_id"]] for i in holdout_kept])
    curve = coverage_risk_curve(holdout_scores, holdout_is_bad)
    console.log(f"Coverage-risk curve: {curve}")


if __name__ == "__main__":
    main()
