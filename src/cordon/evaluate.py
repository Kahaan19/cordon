"""The evaluation harness: run every system on the golden set, compute every §9.3 metric,
write RESULTS.md. BUILD_SPEC.md §9.3.

DECISION: unlike calibrate.py (which fails loudly on a missing bad_to_autosend label because
that IS its whole job), evaluate.py degrades gracefully per-section. Most of §9.3 -- intent
F1, reply-quality judge scores, linter/char-limit compliance, ops -- needs only golden_v1.jsonl
and doesn't touch bad_to_autosend at all. Crashing the entire report over one missing optional
section would throw away everything else that's genuinely computable. See docs/DECISION_LOG.md.

Runs alone: `python -m cordon.evaluate --help`.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from rich.console import Console

from config import CHOSEN_BRAND, GOLDEN_DIR, ROOT
from cordon.agent import load_voice, render_taxonomy, run_agent
from cordon.baselines import b0a_deflector, b0b_coward, b1_nearest_neighbor, b2_obvious_llm, fit_b0, fit_b1
from cordon.calibrate import split_golden_for_calibration
from cordon.index import load_index
from cordon.judge import score_reply
from cordon.linter import MAX_CHARS
from cordon.llm import get_call_log, reset_call_log
from cordon.metrics import (
    confusion_counts, coverage_at_alphas, escalation_metrics, macro_f1_with_ci, ops_metrics,
    per_class_f1, stratum_reweighted_mean,
)
from cordon.sampler import load_split_threads, train_weak_classifier

console = Console()


def rare_intent_true_frequencies(brand: str = CHOSEN_BRAND) -> dict[str, float]:
    """Estimated from the weak classifier's predicted distribution over the test split --
    docs/ANNOTATION_GUIDE.md §1's "computable" sampling-probability requirement for
    rare_intent's inverse-probability weight."""
    pool, _, test = load_split_threads(brand)
    tfidf, clf = train_weak_classifier(pool, brand)
    preds = clf.predict(tfidf.transform([t.first_customer_msg for t in test]))
    counts = np.unique(preds, return_counts=True)
    return {name: float(n) / len(preds) for name, n in zip(*counts)}


def run_system_on_item(system: str, item: dict, ctx: dict) -> tuple:
    """Returns (trace, call_log) for one golden item under one system."""
    reset_call_log()
    message = item["customer_message"]
    if system == "cordon":
        trace = run_agent(message, ctx["index"], ctx["taxonomy_text"], ctx["brand"])
    elif system == "b0a":
        trace = b0a_deflector(message, ctx["majority_intent"], ctx["deflection_reply"], ctx["voice"])
    elif system == "b0b":
        trace = b0b_coward(message, ctx["majority_intent"], ctx["deflection_reply"], ctx["voice"])
    elif system == "b1":
        trace = b1_nearest_neighbor(message, ctx["b1_state"], ctx["voice"])
    elif system == "b2":
        trace = b2_obvious_llm(message, ctx["taxonomy_text"], ctx["brand"], ctx["voice"])
    else:
        raise ValueError(system)
    return trace, get_call_log()


def build_context(brand: str = CHOSEN_BRAND) -> dict:
    pool, calib, _ = load_split_threads(brand)
    ctx = {
        "brand": brand, "index": load_index(brand),
        "taxonomy_text": render_taxonomy(Path("taxonomy/intents.yaml")),
        "voice": load_voice(brand), "b1_state": fit_b1(pool, calib, brand),
    }
    ctx["majority_intent"], ctx["deflection_reply"] = fit_b0(pool)
    return ctx


def evaluate_system(system: str, items: list[dict], ctx: dict, intent_labels: list[str],
                     rare_freq: dict[str, float]) -> tuple[dict, list]:
    traces, call_logs = [], []
    for item in items:
        trace, log = run_system_on_item(system, item, ctx)
        traces.append(trace)
        call_logs.append(log)

    y_true_intent = [i["intent"] for i in items]
    y_pred_intent = [t.intent_pred for t in traces]
    y_true_escalate = [bool(i["should_escalate"]) for i in items]
    y_pred_escalate = [t.decision == "escalate" for t in traces]
    strata = [i["stratum"] for i in items]

    linter_clean_rate = float(np.mean([len(t.linter.violations) == 0 for t in traces if t.linter]))
    char_limit_rate = float(np.mean([len(t.draft_final or "") <= MAX_CHARS for t in traces]))
    unsupported_rates = [t.claim_check.unsupported_claim_rate for t in traces if t.claim_check]
    rubric_scores = [score_reply(i["customer_message"],
                                  t.retrieved[0].agent_reply if t.retrieved else "",
                                  t.draft_final or "")
                      for i, t in zip(items, traces) if t.draft_final]

    metrics = {
        "intent": {
            "macro_f1": macro_f1_with_ci(y_true_intent, y_pred_intent, labels=intent_labels),
            "per_class_f1": per_class_f1(y_true_intent, y_pred_intent, labels=intent_labels),
            "confusion": confusion_counts(y_true_intent, y_pred_intent, labels=intent_labels),
            "macro_f1_natural_only": macro_f1_with_ci(
                [i["intent"] for i, s in zip(items, strata) if s == "natural"],
                [t.intent_pred for t, s in zip(traces, strata) if s == "natural"],
                labels=intent_labels)["macro_f1"] if "natural" in strata else None,
        },
        "escalation": escalation_metrics(y_true_escalate, y_pred_escalate),
        "reply": {
            "unsupported_claim_rate": float(np.mean(unsupported_rates)) if unsupported_rates else 0.0,
            "linter_clean_rate": linter_clean_rate, "char_limit_compliance": char_limit_rate,
            "rubric_means": {d: float(np.mean([s[d] for s in rubric_scores])) for d in
                             (rubric_scores[0].keys() if rubric_scores else [])},
        },
        "ops": ops_metrics(traces, call_logs),
        "stratum_reweighted_escalation_precision": stratum_reweighted_mean(
            [float(p == t) for p, t in zip(y_pred_escalate, y_true_escalate)], strata,
            y_true_intent, rare_freq),
    }
    return metrics, traces


def coverage_curve_or_none(cordon_traces: list, items: list[dict], bad_labels_path: Path) -> list | None:
    if not bad_labels_path.exists():
        console.log(f"[yellow]{bad_labels_path} missing -- skipping coverage-at-alpha "
                     "(needs bad_to_autosend, a separate blind pass per "
                     "docs/ANNOTATION_GUIDE.md §3).[/yellow]")
        return None
    # DECISION: bad_to_autosend_v1.jsonl carries rows for all 5 systems (docs/DECISION_LOG.md) --
    # filter to this system's own rows, or item_ids shared across systems silently collide.
    bad_labels = {r["item_id"]: r["bad_to_autosend"] for r in
                  (json.loads(line) for line in open(bad_labels_path)) if r["system"] == "cordon"}
    scores = np.array([t.risk_score.score if t.risk_score else 1.0 for t in cordon_traces])
    is_bad = np.array([bad_labels.get(i["item_id"], False) for i in items])
    return coverage_at_alphas(["auto" if s <= 0.5 else "escalate" for s in scores], is_bad,
                               [0.01, 0.05, 0.10])


def config_hash() -> str:
    import config as config_module
    return hashlib.sha256(Path(config_module.__file__).read_bytes()).hexdigest()[:12]


def git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                        text=True).strip()[:12]
    except Exception:
        return "unknown"


def write_results_md(results: dict, out_path: Path) -> None:
    lines = [
        "# RESULTS.md -- AUTO-GENERATED, do not edit by hand\n",
        f"git SHA: `{git_sha()}` | generated: {datetime.now(timezone.utc).isoformat()} | "
        f"config hash: `{config_hash()}`\n",
    ]
    for system, metrics in results.items():
        lines.append(f"\n## {system}\n")
        lines.append(f"- Intent macro-F1: {metrics['intent']['macro_f1']['macro_f1']:.3f} "
                     f"[{metrics['intent']['macro_f1']['ci_low']:.3f}, "
                     f"{metrics['intent']['macro_f1']['ci_high']:.3f}] (n={metrics['intent']['macro_f1']['n']})")
        esc = metrics["escalation"]
        lines.append(f"- Escalation P/R/F1: {esc['precision']:.3f} / {esc['recall']:.3f} / "
                     f"{esc['f1']:.3f} [{esc['f1_ci_low']:.3f}, {esc['f1_ci_high']:.3f}]")
        lines.append(f"- Unnecessary escalation rate: {esc['unnecessary_escalation_rate']:.3f} | "
                     f"Missed escalation rate: {esc['missed_escalation_rate']:.3f}")
        rep = metrics["reply"]
        lines.append(f"- unsupported_claim_rate: {rep['unsupported_claim_rate']:.3f} | "
                     f"linter_clean_rate: {rep['linter_clean_rate']:.3f} | "
                     f"char_limit_compliance: {rep['char_limit_compliance']:.3f}")
        lines.append(f"- Rubric means: {rep['rubric_means']}")
        ops = metrics["ops"]
        lines.append(f"- Ops: ${ops['cost_per_1000_tickets']:.2f}/1000 tickets, "
                     f"p50={ops['p50_latency_ms']:.0f}ms, p95={ops['p95_latency_ms']:.0f}ms, "
                     f"cache_hit_rate={ops['cache_hit_rate']:.2f}, "
                     f"tokens/ticket={ops['tokens_per_ticket']:.0f}")
        if metrics.get("coverage_curve") is not None:
            lines.append(f"- Coverage-at-alpha: {metrics['coverage_curve']}")
        else:
            lines.append("- Coverage-at-alpha: N/A -- bad_to_autosend not yet collected")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run every system on the golden set, write RESULTS.md")
    parser.add_argument("--brand", default=CHOSEN_BRAND)
    parser.add_argument("--golden", default=str(GOLDEN_DIR / "golden_v1.jsonl"))
    parser.add_argument("--bad-labels", default=str(GOLDEN_DIR / "bad_to_autosend_v1.jsonl"))
    parser.add_argument("--out", default=str(ROOT / "RESULTS.md"))
    args = parser.parse_args()

    golden_path = Path(args.golden)
    if not golden_path.exists():
        raise FileNotFoundError(f"{golden_path} not found. Label the golden set first: "
                                 "`make label` (docs/ANNOTATION_GUIDE.md).")
    items = [json.loads(line) for line in open(golden_path)]
    _, holdout_items = split_golden_for_calibration(items)
    intent_labels = sorted({i["intent"] for i in items} | {"other"})

    console.log(f"Evaluating on {len(holdout_items)} held-out golden items...")
    ctx = build_context(args.brand)
    rare_freq = rare_intent_true_frequencies(args.brand)

    results = {}
    for system in ("cordon", "b0a", "b0b", "b1", "b2"):
        console.log(f"Running {system}...")
        metrics, traces = evaluate_system(system, holdout_items, ctx, intent_labels, rare_freq)
        metrics["coverage_curve"] = (
            coverage_curve_or_none(traces, holdout_items, Path(args.bad_labels))
            if system == "cordon" else None
        )
        results[system] = metrics

    write_results_md(results, Path(args.out))
    console.log(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
