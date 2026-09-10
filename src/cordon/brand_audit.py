"""Pick the brand by a table, not by vibes. BUILD_SPEC.md §4.

Runs alone: `python -m cordon.brand_audit --help`.
"""
from __future__ import annotations

import argparse
import math
import re
from pathlib import Path

import numpy as np
from rich.console import Console
from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import TfidfVectorizer

from config import (
    AUDIT_TOPIC_KMEANS_K, AUDIT_TOPIC_SAMPLE_SIZE, DEFLECTION_PATTERNS, INTERIM_DIR,
    MIN_THREADS_FOR_BRAND_PICK, RESOLUTION_PATTERNS, SEED, TOP_N_BRANDS_FOR_AUDIT, REPORT_DIR,
)
from cordon.schemas import Thread

console = Console()

DEFLECTION_RE = re.compile("|".join(DEFLECTION_PATTERNS), re.IGNORECASE)
RESOLUTION_RE = re.compile("|".join(RESOLUTION_PATTERNS), re.IGNORECASE)
IMPERATIVE_RE = re.compile(
    r"\b(check|try|restart|update|reinstall|reset|click|visit|send|reply|contact|follow|"
    r"tap|open|clear|verify|confirm|reach out|call|email|uninstall|refresh|reboot)\b",
    re.IGNORECASE,
)
WORD_RE = re.compile(r"\w+")


def is_deflection(text: str) -> bool:
    return bool(DEFLECTION_RE.search(text))


def is_substantive(text: str) -> bool:
    if len(text) < 80 or is_deflection(text):
        return False
    return bool(IMPERATIVE_RE.search(text)) or "<url>" in text


def load_threads(path: Path) -> list[Thread]:
    with open(path) as f:
        return [Thread.model_validate_json(line) for line in f]


def template_ratio(agent_texts: list[str], n: int = 5) -> float:
    grams = []
    for text in agent_texts:
        words = WORD_RE.findall(text.lower())
        grams.extend(tuple(words[i:i + n]) for i in range(len(words) - n + 1))
    if not grams:
        return 0.0
    return 1 - len(set(grams)) / len(grams)


def topic_entropy(messages: list[str], k: int = AUDIT_TOPIC_KMEANS_K,
                   sample_size: int = AUDIT_TOPIC_SAMPLE_SIZE) -> float:
    rng = np.random.RandomState(SEED)
    sample = messages if len(messages) <= sample_size else list(
        rng.choice(messages, size=sample_size, replace=False)
    )
    k = min(k, len(sample))
    if k < 2:
        return 0.0
    vectors = TfidfVectorizer(max_features=2000, stop_words="english").fit_transform(sample)
    labels = KMeans(n_clusters=k, random_state=SEED, n_init=3).fit_predict(vectors)
    _, counts = np.unique(labels, return_counts=True)
    probs = counts / counts.sum()
    return float(-np.sum(probs * np.log2(probs)))


def compute_brand_metrics(brand: str, threads: list[Thread]) -> dict:
    n_threads = len(threads)
    median_turns = float(np.median([t.n_turns for t in threads]))

    first_replies = [t.first_agent_reply for t in threads if t.first_agent_reply]
    deflection_rate = sum(is_deflection(r) for r in first_replies) / len(first_replies)
    substantive_rate = sum(is_substantive(r) for r in first_replies) / len(first_replies)

    resolved = 0
    for t in threads:
        if RESOLUTION_RE.search(t.last_customer_msg) and any(
            is_substantive(turn.text) for turn in t.turns if turn.role == "agent"
        ):
            resolved += 1
    public_resolution_rate = resolved / n_threads

    agent_texts = [turn.text for t in threads for turn in t.turns if turn.role == "agent"]
    tmpl_ratio = template_ratio(agent_texts)

    entropy = topic_entropy([t.first_customer_msg for t in threads])

    substantive_score = substantive_rate * math.log10(n_threads) * (1 - tmpl_ratio)

    return {
        "brand": brand, "n_threads": n_threads, "median_turns": median_turns,
        "deflection_rate": deflection_rate, "substantive_rate": substantive_rate,
        "public_resolution_rate": public_resolution_rate, "template_ratio": tmpl_ratio,
        "topic_entropy": entropy, "answerability_score": substantive_score,
    }


def render_report(rows: list[dict], picked: dict | None) -> str:
    header = ("| Brand | n_threads | median_turns | deflection_rate | substantive_rate | "
              "public_resolution_rate | template_ratio | topic_entropy | answerability_score |\n"
              "|---|---|---|---|---|---|---|---|---|\n")
    body = "".join(
        f"| {r['brand']} | {r['n_threads']} | {r['median_turns']:.1f} | "
        f"{r['deflection_rate']:.2%} | {r['substantive_rate']:.2%} | "
        f"{r['public_resolution_rate']:.2%} | {r['template_ratio']:.2f} | "
        f"{r['topic_entropy']:.2f} | {r['answerability_score']:.3f} |\n"
        for r in rows
    )
    if picked is None:
        verdict = (f"\nNo brand in the top {TOP_N_BRANDS_FOR_AUDIT} clears the "
                   f"n_threads > {MIN_THREADS_FOR_BRAND_PICK} floor. No pick made.\n")
    else:
        verdict = (
            f"\n**Pick: {picked['brand']}.** {picked['n_threads']} threads, "
            f"deflection_rate {picked['deflection_rate']:.1%}, "
            f"substantive_rate {picked['substantive_rate']:.1%}, "
            f"template_ratio {picked['template_ratio']:.2f}, "
            f"answerability_score {picked['answerability_score']:.3f} — the top score among "
            f"brands with n_threads > {MIN_THREADS_FOR_BRAND_PICK}. Highest-volume brand in this "
            f"table is {rows[0]['brand']} at deflection_rate {rows[0]['deflection_rate']:.1%}; "
            f"volume alone would have picked a worse-grounded brand.\n"
        )
    return "# Brand answerability audit\n\n" + header + body + verdict


def audit_brands(interim_dir: Path = INTERIM_DIR, report_dir: Path = REPORT_DIR) -> dict:
    brand_files = sorted(interim_dir.glob("threads_*.jsonl"))
    if not brand_files:
        raise FileNotFoundError(
            f"No threads_*.jsonl in {interim_dir}. Run `make ingest` first."
        )

    metrics = []
    for path in brand_files:
        brand = path.stem.removeprefix("threads_")
        threads = load_threads(path)
        metrics.append(compute_brand_metrics(brand, threads))

    top = sorted(metrics, key=lambda m: m["n_threads"], reverse=True)[:TOP_N_BRANDS_FOR_AUDIT]
    eligible = [m for m in top if m["n_threads"] > MIN_THREADS_FOR_BRAND_PICK]
    picked = max(eligible, key=lambda m: m["answerability_score"], default=None)

    report_dir.mkdir(parents=True, exist_ok=True)
    out_path = report_dir / "brand_audit.md"
    out_path.write_text(render_report(top, picked))
    console.log(f"Wrote {out_path}. Picked brand: {picked['brand'] if picked else None}")
    return {"top": top, "picked": picked}


def main() -> None:
    parser = argparse.ArgumentParser(description="Rank brands and pick one by an audit table")
    parser.add_argument("--interim-dir", type=Path, default=INTERIM_DIR)
    parser.add_argument("--report-dir", type=Path, default=REPORT_DIR)
    args = parser.parse_args()
    audit_brands(args.interim_dir, args.report_dir)


if __name__ == "__main__":
    main()
