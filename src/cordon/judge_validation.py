"""Trap set + bias probes for the judge, built on judge.py's primitives. BUILD_SPEC.md §9.4.2,
§9.4.3.

All defect injections are deterministic text transforms, not LLM-generated -- keeps the trap
set reproducible and not confounded by another model's quality variance. "Detected" means the
defect's mapped rubric dimension (config.DEFECT_TO_DIMENSION) scores strictly lower on the
defective copy than the original -- this tests the *actual* production rubric's sensitivity,
not a separate defect-classifier nobody else uses.

Runs alone: `python -m cordon.judge_validation --help`.
"""
from __future__ import annotations

import argparse
import random
from pathlib import Path

import numpy as np
from rich.console import Console

from config import (
    BIAS_PROBE_SAMPLE_SIZE, CHOSEN_BRAND, DEFECT_TO_DIMENSION, LENGTH_PROBE_FILLER,
    REPORT_DIR, RUBRIC_DIMENSIONS, SEED, TRAP_SET_SIZE,
)
from cordon.agent import load_voice
from cordon.baselines import b1_nearest_neighbor, fit_b1
from cordon.index import load_index
from cordon.judge import compare_pair, score_reply
from cordon.llm import JUDGE_MODEL, complete
from cordon.playbook import assign_intents, intent_centroids
from cordon.sampler import load_split_threads

console = Console()


def inject_defect(defect: str, reply: str, other_reply: str) -> str:
    if defect == "invented_policy":
        return reply + " Per our policy, all devices are eligible for a free upgrade this month."
    if defect == "wrong_intent":
        return other_reply
    if defect == "pii_request":
        return reply + " Please reply with your account email and phone number so we can verify you."
    if defect == "unbounded_promise":
        return reply + " We guarantee this will be fully resolved within 24 hours."
    if defect == "wrong_signoff_voice":
        return "We regret to inform you of this matter. " + reply.replace("!", ".") + " ^XY"
    if defect == "truncated_mid_sentence":
        return reply[:max(10, int(len(reply) * 0.6))]
    if defect == "subtly_wrong_product_name":
        return reply + " Note this only applies to Netflix subscribers."
    raise ValueError(defect)


def build_trap_set(brand: str = CHOSEN_BRAND, n: int = TRAP_SET_SIZE, seed: int = SEED) -> list[dict]:
    """~n real, substantive replies from the retrieval index, each paired with a same-index
    reply from a different intent (for the wrong_intent defect)."""
    index = load_index(brand)
    vectors, meta = index["vectors"], index["meta"]
    intents = assign_intents(vectors, intent_centroids(brand))
    by_intent: dict[str, list[int]] = {}
    for i, intent in enumerate(intents):
        by_intent.setdefault(intent, []).append(i)

    rng = random.Random(seed)
    idx = rng.sample(range(len(meta)), min(n, len(meta)))
    items = []
    for i in idx:
        other_intents = [name for name in by_intent if name != intents[i]]
        other_i = rng.choice(by_intent[rng.choice(other_intents)])
        reply = meta.iloc[i]["substantive_agent_reply"]
        items.append({
            "message": meta.iloc[i]["first_customer_msg"], "evidence": reply, "good_reply": reply,
            "other_reply": meta.iloc[other_i]["substantive_agent_reply"],
        })
    return items


def measure_trap_detection(trap_items: list[dict]) -> dict[str, float]:
    detection = {defect: [] for defect in DEFECT_TO_DIMENSION}
    for item in trap_items:
        good_scores = score_reply(item["message"], item["evidence"], item["good_reply"])
        for defect, dim in DEFECT_TO_DIMENSION.items():
            defective = inject_defect(defect, item["good_reply"], item["other_reply"])
            bad_scores = score_reply(item["message"], item["evidence"], defective)
            detection[defect].append(bad_scores[dim] < good_scores[dim])
    return {defect: sum(hits) / len(hits) for defect, hits in detection.items()}


def position_bias_probe(trap_items: list[dict], rng: random.Random,
                         n: int = BIAS_PROBE_SAMPLE_SIZE) -> float:
    """Swap A/B order for the same (good, defective) pair; report how often the winning TEXT
    (not letter) changes just because of order."""
    sample = rng.sample(trap_items, min(n, len(trap_items)))
    flips = 0
    for item in sample:
        defective = inject_defect("unbounded_promise", item["good_reply"], item["other_reply"])
        ab = compare_pair(item["message"], item["evidence"], item["good_reply"], defective)
        ba = compare_pair(item["message"], item["evidence"], defective, item["good_reply"])
        winner_ab = {"A": "good", "B": "defective", "tie": "tie"}[ab]
        winner_ba = {"A": "defective", "B": "good", "tie": "tie"}[ba]
        flips += winner_ab != winner_ba
    return flips / len(sample)


def length_bias_probe(trap_items: list[dict], rng: random.Random,
                       n: int = BIAS_PROBE_SAMPLE_SIZE) -> dict[str, float]:
    """Pad a real reply with harmless filler; report the per-dimension score delta."""
    sample = rng.sample(trap_items, min(n, len(trap_items)))
    deltas = {d: [] for d in RUBRIC_DIMENSIONS}
    for item in sample:
        base = score_reply(item["message"], item["evidence"], item["good_reply"])
        padded = score_reply(item["message"], item["evidence"], item["good_reply"] + LENGTH_PROBE_FILLER)
        for d in RUBRIC_DIMENSIONS:
            deltas[d].append(padded[d] - base[d])
    return {d: float(np.mean(v)) for d, v in deltas.items()}


def self_preference_probe(trap_items: list[dict], b1_state: dict, voice: dict,
                           rng: random.Random, n: int = BIAS_PROBE_SAMPLE_SIZE) -> dict[str, float]:
    """The judge (qwen3) drafts its own reply, then blind-scores its own draft vs. the real
    historical reply vs. B1's copied reply -- same-family bias (BUILD_SPEC.md §9.4.3c, §2)."""
    sample = rng.sample(trap_items, min(n, len(trap_items)))
    scores: dict[str, list[float]] = {"qwen_draft": [], "real_reply": [], "b1_copied": []}
    for item in sample:
        qwen_draft = complete(
            "Reply to this customer support message in under 280 characters, in a helpful, "
            f"professional support-agent voice: {item['message']}",
            model=JUDGE_MODEL, provider="ollama",
        ).text.strip()
        b1_reply = b1_nearest_neighbor(item["message"], b1_state, voice).draft_final
        for label, text in [("qwen_draft", qwen_draft), ("real_reply", item["good_reply"]),
                             ("b1_copied", b1_reply)]:
            s = score_reply(item["message"], item["evidence"], text)
            scores[label].append(float(np.mean(list(s.values()))))
    return {label: float(np.mean(v)) for label, v in scores.items()}


def main() -> None:
    parser = argparse.ArgumentParser(description="Trap set + bias probes for the judge")
    parser.add_argument("--brand", default=CHOSEN_BRAND)
    parser.add_argument("--trap-n", type=int, default=TRAP_SET_SIZE)
    parser.add_argument("--probe-n", type=int, default=BIAS_PROBE_SAMPLE_SIZE)
    parser.add_argument("--out", type=str, default=str(REPORT_DIR / "judge_validation.md"))
    args = parser.parse_args()

    rng = random.Random(SEED)
    voice = load_voice(args.brand)

    console.log(f"Building trap set (n={args.trap_n})...")
    trap_items = build_trap_set(args.brand, args.trap_n)

    console.log("Measuring per-defect detection rate...")
    detection = measure_trap_detection(trap_items)
    for defect, rate in detection.items():
        console.log(f"  {defect}: {rate:.0%}")

    console.log("Position-bias probe...")
    flip_rate = position_bias_probe(trap_items, rng, args.probe_n)
    console.log(f"  flip_rate: {flip_rate:.0%}")

    console.log("Length-bias probe...")
    length_deltas = length_bias_probe(trap_items, rng, args.probe_n)
    console.log(f"  score deltas after padding: {length_deltas}")

    console.log("Fitting B1 for the self-preference probe...")
    pool, calib, _ = load_split_threads(args.brand)
    b1_state = fit_b1(pool, calib, args.brand)

    console.log("Self-preference probe...")
    self_pref = self_preference_probe(trap_items, b1_state, voice, rng, args.probe_n)
    console.log(f"  mean scores by source: {self_pref}")

    write_report(detection, flip_rate, length_deltas, self_pref, len(trap_items), args.probe_n,
                 Path(args.out))
    console.log(f"Wrote {args.out}")


def write_report(detection: dict, flip_rate: float, length_deltas: dict, self_pref: dict,
                  trap_n: int, probe_n: int, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Judge validation (BUILD_SPEC.md §9.4)\n",
             f"## Trap set (n={trap_n}, real substantive replies, deterministic defect injection)\n",
             "| defect | dimension | detection rate |", "|---|---|---|"]
    for defect, rate in sorted(detection.items(), key=lambda kv: -kv[1]):
        lines.append(f"| {defect} | {DEFECT_TO_DIMENSION[defect]} | {rate:.0%} |")
    lines += [
        f"\n## Position-bias probe (n={probe_n})\n",
        f"Flip rate: **{flip_rate:.0%}** -- how often swapping which side (A/B) two replies "
        "appear on changes the pairwise winner.\n",
        f"\n## Length-bias probe (n={probe_n})\n",
        "Score delta after padding a real reply with content-free filler:\n",
        "| dimension | delta |", "|---|---|",
    ]
    lines += [f"| {d} | {v:+.2f} |" for d, v in length_deltas.items()]
    lines += [
        f"\n## Self-preference probe (n={probe_n})\n",
        "Mean rubric score (averaged across all 5 dimensions), blind, by reply source:\n",
        "| source | mean score |", "|---|---|",
    ]
    lines += [f"| {label} | {v:.2f} |" for label, v in self_pref.items()]
    out_path.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
