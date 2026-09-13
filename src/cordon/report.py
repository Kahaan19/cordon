"""Reviewer-facing HTML: report/traces.html and report/index.html. BUILD_SPEC.md §10 items 2-3.

Rendered from REAL golden_v1.jsonl + a real CORDON run -- never from placeholder data. Fails
loudly if golden_v1.jsonl is missing, same as calibrate.py/evaluate.py. Sections needing a
second annotation pass not yet collected (coverage-risk curve and cost-sensitivity need
bad_to_autosend; judge agreement needs 80 human-scored items) render an honest "not yet
available" state -- the same graceful, per-section degradation evaluate.py already uses, never
a fabricated number standing in for missing data.

Runs alone: `python -m cordon.report --help`.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from rich.console import Console

from config import CHOSEN_BRAND, GOLDEN_DIR, REPORT_DIR, RISK_COST_RATIOS
from cordon.calibrate import coverage_risk_curve, expected_saving, split_golden_for_calibration
from cordon.evaluate import build_context, config_hash, git_sha, run_system_on_item
from cordon.judge import score_reply
from cordon.metrics import confusion_counts
from cordon.report_index_html import render_index_html
from cordon.report_traces_html import render_traces_html

console = Console()


def gather_item_data(items: list[dict], ctx: dict) -> list[dict]:
    """One record per golden item: gold labels + CORDON's real trace + judge scores + pass/fail."""
    records = []
    for item in items:
        trace, _ = run_system_on_item("cordon", item, ctx)
        evidence = trace.retrieved[0].agent_reply if trace.retrieved else ""
        judge_scores = (score_reply(item["customer_message"], evidence, trace.draft_final)
                         if trace.draft_final else None)
        correct = (trace.intent_pred == item["intent"]
                   and (trace.decision == "escalate") == bool(item["should_escalate"]))
        records.append({"item": item, "trace": trace, "judge_scores": judge_scores,
                         "correct": correct})
    return records


def compute_cost_sensitivity(scores: np.ndarray, is_bad: np.ndarray,
                              cost_ratios: list[float] = RISK_COST_RATIOS) -> list[dict]:
    """Optimal threshold per bad-reply cost ratio. BUILD_SPEC.md §8 business framing."""
    taus = sorted(set(scores.tolist()))
    results = []
    for cb in cost_ratios:
        best_tau, best_saving = 0.0, float("-inf")
        for tau in taus:
            auto = scores <= tau
            n = int(auto.sum())
            if n == 0:
                continue
            p_bad = float((is_bad & auto).sum()) / n
            saving = expected_saving(n / len(scores), p_bad, cb)
            if saving > best_saving:
                best_saving, best_tau = saving, tau
        results.append({"cost_ratio": cb, "optimal_tau": best_tau, "expected_saving": best_saving})
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Render report/traces.html and report/index.html")
    parser.add_argument("--brand", default=CHOSEN_BRAND)
    parser.add_argument("--golden", default=str(GOLDEN_DIR / "golden_v1.jsonl"))
    parser.add_argument("--bad-labels", default=str(GOLDEN_DIR / "bad_to_autosend_v1.jsonl"))
    parser.add_argument("--judge-agreement", default=str(GOLDEN_DIR / "judge_agreement_v1.jsonl"))
    parser.add_argument("--out-dir", default=str(REPORT_DIR))
    args = parser.parse_args()

    golden_path = Path(args.golden)
    if not golden_path.exists():
        raise FileNotFoundError(f"{golden_path} not found. Label the golden set first: "
                                 "`make label` (docs/ANNOTATION_GUIDE.md).")
    items = [json.loads(line) for line in open(golden_path)]
    _, holdout_items = split_golden_for_calibration(items)
    intent_labels = sorted({i["intent"] for i in items} | {"other"})

    console.log(f"Running CORDON on {len(holdout_items)} held-out golden items...")
    ctx = build_context(args.brand)
    records = gather_item_data(holdout_items, ctx)

    confusion = confusion_counts([r["item"]["intent"] for r in records],
                                  [r["trace"].intent_pred for r in records], labels=intent_labels)

    coverage_curve, cost_sensitivity = None, None
    bad_labels_path = Path(args.bad_labels)
    if bad_labels_path.exists():
        # DECISION: bad_to_autosend_v1.jsonl carries rows for all 5 systems (docs/DECISION_LOG.md)
        # -- filter to this system's own rows, or item_ids shared across systems silently collide.
        bad_labels = {r["item_id"]: r["bad_to_autosend"] for r in
                      (json.loads(line) for line in open(bad_labels_path)) if r["system"] == "cordon"}
        scores = np.array([r["trace"].risk_score.score if r["trace"].risk_score else 1.0
                            for r in records])
        is_bad = np.array([bad_labels.get(r["item"]["item_id"], False) for r in records])
        coverage_curve = coverage_risk_curve(scores, is_bad)
        cost_sensitivity = compute_cost_sensitivity(scores, is_bad)
    else:
        console.log(f"[yellow]{bad_labels_path} missing -- coverage-risk curve and "
                     "cost-sensitivity will render as not-yet-available.[/yellow]")

    judge_agreement_path = Path(args.judge_agreement)
    judge_agreement = ([json.loads(line) for line in open(judge_agreement_path)]
                        if judge_agreement_path.exists() else None)
    if judge_agreement is None:
        console.log(f"[yellow]{judge_agreement_path} missing -- judge agreement will render "
                     "as not-yet-available.[/yellow]")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    header = f"git SHA: {git_sha()} | config hash: {config_hash()}"

    (out_dir / "traces.html").write_text(render_traces_html(records, header))
    (out_dir / "index.html").write_text(
        render_index_html(confusion, coverage_curve, cost_sensitivity, judge_agreement, header))
    console.log(f"Wrote {out_dir}/traces.html and {out_dir}/index.html")


if __name__ == "__main__":
    main()
