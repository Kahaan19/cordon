"""Finds every auto-handled draft across all 5 systems and builds the blind labelling queue
for bad_to_autosend. BUILD_SPEC.md §8, docs/ANNOTATION_GUIDE.md §3.

"Label it blind to which system produced the draft -- shuffle and strip system IDs before
labelling" -- but the underlying file still records which system each draft came from
(bad_to_autosend_labeler.py just never displays it), since calibrate.py/evaluate.py/report.py
need to know whose coverage-risk curve a given label belongs to.

B0a's auto-handled drafts are derived automatically from should_escalate, never queued for a
human (config.BAD_TO_AUTOSEND_DERIVED_SYSTEMS; docs/DECISION_LOG.md). B0b never auto-handles by
design, so it always contributes zero items -- not a derivation, just an empty set.

Runs alone: `python -m cordon.bad_to_autosend_sampler --help`.
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from rich.console import Console

from config import (
    BAD_TO_AUTOSEND_DERIVED_SYSTEMS, CHOSEN_BRAND, GOLDEN_DIR, REPORT_DIR, SEED,
)
from cordon.calibrate import split_golden_for_calibration
from cordon.evaluate import build_context, run_system_on_item

console = Console()

SYSTEMS = ("cordon", "b0a", "b0b", "b1", "b2")


def run_all_systems(items: list[dict], ctx: dict) -> dict[str, list]:
    """One real run per (system, item). Cached after the first pass, same as everywhere else."""
    traces_by_system: dict[str, list] = {s: [] for s in SYSTEMS}
    for system in SYSTEMS:
        for item in items:
            trace, _ = run_system_on_item(system, item, ctx)
            traces_by_system[system].append(trace)
    return traces_by_system


def auto_handled_counts(items: list[dict], traces_by_system: dict[str, list]) -> dict[str, int]:
    return {system: sum(1 for t in traces if t.decision == "auto")
            for system, traces in traces_by_system.items()}


def derive_bad_to_autosend(item: dict) -> bool:
    """Proven equivalent to should_escalate for BAD_TO_AUTOSEND_DERIVED_SYSTEMS -- see
    config.py's decision comment for the evidence."""
    return bool(item["should_escalate"])


def _needs_label(system: str, trace) -> bool:
    """DECISION: CORDON's threshold gets swept by calibrate.py's choose_threshold over its
    FULL score range, not just the subset currently decision=="auto" under today's placeholder
    0.5 -- so CORDON needs a label for every non-hard-overridden item (risk_score is not None),
    or the sweep silently has no ground truth for higher candidate tau values. Baselines have
    no swept threshold (their "auto" decision is fixed policy), so decision=="auto" is the
    right, narrower filter for them. See docs/DECISION_LOG.md."""
    if system == "cordon":
        return trace.risk_score is not None
    return trace.decision == "auto"


def build_queue_and_derived(items: list[dict], traces_by_system: dict[str, list],
                             seed: int = SEED) -> tuple[list[dict], list[dict]]:
    derived, queue = [], []
    for system, traces in traces_by_system.items():
        for item, trace in zip(items, traces):
            if not _needs_label(system, trace):
                continue
            if system in BAD_TO_AUTOSEND_DERIVED_SYSTEMS:
                derived.append({"item_id": item["item_id"], "system": system,
                                 "bad_to_autosend": derive_bad_to_autosend(item)})
                continue
            evidence = trace.retrieved[0].agent_reply if trace.retrieved else ""
            queue.append({
                "label_id": f"{item['item_id']}__{system}", "item_id": item["item_id"],
                "system": system,  # present in the file, never shown by the labeller
                "customer_message": item["customer_message"], "evidence": evidence,
                "draft": trace.draft_final,
            })
    random.Random(seed).shuffle(queue)
    return queue, derived


def write_counts_report(counts: dict[str, int], queue: list[dict], derived: list[dict],
                         out_path: Path = REPORT_DIR / "bad_to_autosend_counts.md") -> None:
    """DECISION: "auto-handled (today's policy)" and "needs a label" are DIFFERENT numbers for
    cordon specifically -- its threshold gets swept over its full score range by
    choose_threshold, so it needs a label for every non-hard-overridden item, not just the ones
    decision=="auto" under today's placeholder 0.5. Reporting both, not just one, so this isn't
    a silent surprise later. See _needs_label()'s docstring and docs/DECISION_LOG.md."""
    from collections import Counter
    n_needing_label = Counter(r["system"] for r in queue + derived)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# bad_to_autosend: auto-handled drafts per system\n",
             "| system | auto-handled (today's policy) | needs a label | how |", "|---|---|---|---|"]
    for system in SYSTEMS:
        how = ("derived from should_escalate" if system in BAD_TO_AUTOSEND_DERIVED_SYSTEMS
               else "blind human pass")
        lines.append(f"| {system} | {counts[system]} | {n_needing_label.get(system, 0)} | {how} |")
    lines.append(f"\nQueued for blind human labelling: **{len(queue)}**. Derived automatically: "
                 f"**{len(derived)}**.")
    out_path.write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the bad_to_autosend blind labelling queue")
    parser.add_argument("--brand", default=CHOSEN_BRAND)
    parser.add_argument("--golden", default=str(GOLDEN_DIR / "golden_v1.jsonl"))
    parser.add_argument("--queue-out", default=str(GOLDEN_DIR / "bad_to_autosend_queue.jsonl"))
    parser.add_argument("--labels-out", default=str(GOLDEN_DIR / "bad_to_autosend_v1.jsonl"))
    parser.add_argument("--counts-out", default=str(REPORT_DIR / "bad_to_autosend_counts.md"))
    args = parser.parse_args()

    golden_path = Path(args.golden)
    if not golden_path.exists():
        raise FileNotFoundError(f"{golden_path} not found. Label the golden set first: "
                                 "`make label` (docs/ANNOTATION_GUIDE.md).")
    items = [json.loads(line) for line in open(golden_path)]
    _, holdout_items = split_golden_for_calibration(items)

    console.log(f"Running all {len(SYSTEMS)} systems on {len(holdout_items)} held-out items...")
    ctx = build_context(args.brand)
    traces_by_system = run_all_systems(holdout_items, ctx)

    counts = auto_handled_counts(holdout_items, traces_by_system)
    console.log(f"Auto-handled counts: {counts}")

    queue, derived = build_queue_and_derived(holdout_items, traces_by_system)
    write_counts_report(counts, queue, derived, Path(args.counts_out))
    console.log(f"Queued {len(queue)} items for blind labelling; derived {len(derived)} "
                f"automatically ({BAD_TO_AUTOSEND_DERIVED_SYSTEMS}).")

    labels_path = Path(args.labels_out)
    already = set()
    if labels_path.exists():
        already = {(r["item_id"], r["system"]) for r in
                   (json.loads(line) for line in open(labels_path))}
    with open(labels_path, "a") as f:
        for row in derived:
            if (row["item_id"], row["system"]) not in already:
                f.write(json.dumps(row) + "\n")

    with open(args.queue_out, "w") as f:
        for row in queue:
            f.write(json.dumps(row) + "\n")
    console.log(f"Wrote {args.queue_out} (labeller input) and appended derived rows to "
                f"{labels_path}")


if __name__ == "__main__":
    main()
