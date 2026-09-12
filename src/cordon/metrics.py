"""Bootstrap-CI'd statistical primitives for the §9.3 metric suite. BUILD_SPEC.md §9.3.

Every headline number carries a CI (bootstrap, 2000 resamples, paired -- resampling (y_true,
y_pred) together, never independently). Kept generic and side-effect-free: evaluate.py supplies
the data, these functions just compute.

Runs alone: `python -m cordon.metrics --help` (smoke-tests bootstrap_ci_paired on toy data).
"""
from __future__ import annotations

import argparse
from collections import Counter

import numpy as np
from rich.console import Console
from sklearn.metrics import f1_score, precision_score, recall_score

from config import BOOTSTRAP_CI, BOOTSTRAP_N_RESAMPLES, SEED

console = Console()


def bootstrap_ci_paired(arrays: tuple[np.ndarray, ...], statistic_fn, n_resamples: int = BOOTSTRAP_N_RESAMPLES,
                         ci: float = BOOTSTRAP_CI, seed: int = SEED) -> tuple[float, float, float]:
    """Resamples all arrays together (paired), so a metric over (y_true, y_pred) resamples
    matched pairs, not independent columns. BUILD_SPEC.md §9.3: 2000 resamples, every headline
    number carries a CI."""
    rng = np.random.RandomState(seed)
    arrays = tuple(np.asarray(a) for a in arrays)
    n = len(arrays[0])
    point = statistic_fn(*arrays)
    boot = [statistic_fn(*[a[rng.randint(0, n, size=n)] for a in arrays]) for _ in range(n_resamples)]
    tail = (1 - ci) / 2 * 100
    lower, upper = np.percentile(boot, [tail, 100 - tail])
    return float(point), float(lower), float(upper)


def macro_f1_with_ci(y_true: list, y_pred: list, labels: list[str] | None = None) -> dict:
    def stat(yt, yp):
        return f1_score(yt, yp, labels=labels, average="macro", zero_division=0)
    point, lo, hi = bootstrap_ci_paired((np.array(y_true), np.array(y_pred)), stat)
    return {"macro_f1": point, "ci_low": lo, "ci_high": hi, "n": len(y_true)}


def per_class_f1(y_true: list, y_pred: list, labels: list[str]) -> dict[str, dict]:
    scores = f1_score(y_true, y_pred, labels=labels, average=None, zero_division=0)
    counts = Counter(y_true)
    return {label: {"f1": float(s), "n": counts.get(label, 0)} for label, s in zip(labels, scores)}


def confusion_counts(y_true: list, y_pred: list, labels: list[str]) -> dict[str, dict[str, int]]:
    idx = {label: i for i, label in enumerate(labels)}
    matrix = np.zeros((len(labels), len(labels)), dtype=int)
    for t, p in zip(y_true, y_pred):
        if t in idx and p in idx:
            matrix[idx[t], idx[p]] += 1
    return {t: {p: int(matrix[idx[t], idx[p]]) for p in labels} for t in labels}


def escalation_metrics(y_true: list[bool], y_pred: list[bool]) -> dict:
    """Both sides, per BUILD_SPEC.md §9.3: unnecessary escalation wastes human time, a missed
    one lets harm through."""
    yt, yp = np.array(y_true, dtype=bool), np.array(y_pred, dtype=bool)

    def f1_stat(a, b):
        return f1_score(a, b, zero_division=0)
    f1, f1_lo, f1_hi = bootstrap_ci_paired((yt, yp), f1_stat)

    return {
        "precision": float(precision_score(yt, yp, zero_division=0)),
        "recall": float(recall_score(yt, yp, zero_division=0)),
        "f1": f1, "f1_ci_low": f1_lo, "f1_ci_high": f1_hi,
        "unnecessary_escalation_rate": float(np.mean(yp & ~yt)),  # escalated but didn't need to
        "missed_escalation_rate": float(np.mean(~yp & yt)),  # should have escalated, didn't
        "n": len(yt),
    }


def coverage_at_alphas(decisions: list[str], is_bad: list[bool], alphas: list[float]) -> dict[float, float]:
    """Coverage at fixed risk budgets, for systems with no continuous risk score (baselines) --
    just the empirical auto-decision bad-rate compared against each alpha directly, since
    there's no threshold to sweep. BUILD_SPEC.md §9.3."""
    auto = np.array([d == "auto" for d in decisions])
    bad = np.array(is_bad, dtype=bool)
    n_auto = int(auto.sum())
    bad_rate = float((bad & auto).sum() / n_auto) if n_auto else 0.0
    return {alpha: (n_auto / len(decisions) if bad_rate <= alpha else 0.0) for alpha in alphas}


def stratum_reweighted_mean(values: list[float], strata: list[str], intents: list[str],
                             rare_intent_true_freq: dict[str, float]) -> float:
    """docs/ANNOTATION_GUIDE.md §1: natural weight 1.0, rare_intent weighted by true class
    frequency, hard/redteam weight 0 for distributional claims -- never folded into a headline
    without saying so."""
    weights = []
    for stratum, intent in zip(strata, intents):
        if stratum == "natural":
            weights.append(1.0)
        elif stratum == "rare_intent":
            weights.append(rare_intent_true_freq.get(intent, 0.0))
        else:
            weights.append(0.0)
    weights = np.array(weights)
    if weights.sum() == 0:
        return float("nan")
    return float(np.average(values, weights=weights))


def ops_metrics(traces: list, call_logs: list[list[dict]]) -> dict:
    """$/1000 tickets, p50/p95 latency, cache hit-rate, tokens/ticket. BUILD_SPEC.md §9.3."""
    latencies = np.array([t.latency_ms for t in traces])
    costs = np.array([t.cost_usd for t in traces])
    all_calls = [c for log in call_logs for c in log]
    n_calls = len(all_calls)
    cache_hit_rate = float(np.mean([c["cache_hit"] for c in all_calls])) if n_calls else float("nan")
    tokens_per_ticket = float(np.mean([sum(c["input_tokens"] + c["output_tokens"] for c in log)
                                        for log in call_logs])) if call_logs else 0.0
    return {
        "cost_per_1000_tickets": float(costs.mean() * 1000) if len(costs) else 0.0,
        "p50_latency_ms": float(np.percentile(latencies, 50)) if len(latencies) else 0.0,
        "p95_latency_ms": float(np.percentile(latencies, 95)) if len(latencies) else 0.0,
        "cache_hit_rate": cache_hit_rate, "tokens_per_ticket": tokens_per_ticket,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke-test bootstrap_ci_paired on toy data")
    parser.parse_args()
    y_true = ["a", "b", "a", "b", "a", "b", "a", "a"]
    y_pred = ["a", "b", "a", "a", "a", "b", "b", "a"]
    console.print(macro_f1_with_ci(y_true, y_pred, labels=["a", "b"]))


if __name__ == "__main__":
    main()
