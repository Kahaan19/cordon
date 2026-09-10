"""Merge induced clusters into a final taxonomy and check its stability. BUILD_SPEC.md §5 steps
5-6 + the taxonomy stability check.

Given a merge map (cluster_id -> intent name, or "other") for the clustering `taxonomy.py`
already printed, write taxonomy/intents.yaml and re-cluster at other seeds/k to report Adjusted
Rand Index against the final taxonomy.

Runs alone: `python -m cordon.taxonomy_finalize --help`.
"""
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

import numpy as np
import yaml
from rich.console import Console
from sklearn.metrics import adjusted_rand_score

from config import (
    CHOSEN_BRAND, TAXONOMY_DIR, TAXONOMY_KMEANS_K, TAXONOMY_STABILITY_KS,
    TAXONOMY_STABILITY_SEEDS,
)
from cordon.llm import GEN_MODEL, complete, load_prompt
from cordon.taxonomy import cluster, induce

console = Console()

CONSOLIDATE_SCHEMA = {
    "type": "object",
    "properties": {
        "definition": {"type": "string"},
        "include": {"type": "string"},
        "exclude": {"type": "string"},
    },
    "required": ["definition", "include", "exclude"],
}


def consolidate_intent(brand: str, intent_name: str, members: list[dict]) -> dict:
    """Synthesize N merged clusters' descriptions into one clean {definition, include, exclude}
    -- never hand-typed, only ever re-stating what the per-cluster LLM outputs already said."""
    members_text = "\n".join(
        f"- name: {m['name']}\n  definition: {m['one_line_definition']}\n"
        f"  include: {m['inclusion_criteria']}\n  exclude: {m['exclusion_criteria']}"
        for m in members
    )
    prompt = (load_prompt("intent_consolidate")
              .replace("{{BRAND}}", brand).replace("{{INTENT_NAME}}", intent_name)
              .replace("{{MEMBERS}}", members_text))
    return complete(prompt, model=GEN_MODEL, schema=CONSOLIDATE_SCHEMA).parsed


def finalize(induced: dict, merge_map: dict[int, str],
             out_path: Path = TAXONOMY_DIR / "intents.yaml",
             boundary_notes: dict[str, str] | None = None) -> np.ndarray:
    """8-10 named intents + 'other'. Write taxonomy/intents.yaml (BUILD_SPEC.md §5 step 6)."""
    clusters_by_id = {c["cluster_id"]: c for c in induced["clusters"]}
    final_labels = np.array([merge_map[int(label)] for label in induced["labels"]], dtype=object)
    vectors, tweet_ids = induced["vectors"], induced["tweet_ids"]

    intents = []
    for intent_name in sorted(set(merge_map.values())):
        members = [clusters_by_id[cid] for cid, name in merge_map.items() if name == intent_name]
        idx = np.where(final_labels == intent_name)[0]

        if intent_name == "other":
            definition = "Doesn't fit a named intent -- junk, off-topic, or too mixed to resolve."
            include, exclude = ("Not covered by another intent's inclusion criteria.",
                                 "None -- this is the residual bucket.")
        elif len(members) > 1:
            consolidated = consolidate_intent(CHOSEN_BRAND, intent_name, members)
            definition, include, exclude = (consolidated["definition"], consolidated["include"],
                                              consolidated["exclude"])
        else:
            definition = members[0]["one_line_definition"]
            include, exclude = members[0]["inclusion_criteria"], members[0]["exclusion_criteria"]

        if boundary_notes and intent_name in boundary_notes:
            exclude = f"{exclude} | {boundary_notes[intent_name]}"

        centroid = vectors[idx].mean(axis=0)
        positive = idx[np.argsort(np.linalg.norm(vectors[idx] - centroid, axis=1))][:3]

        other_idx = np.where(final_labels != intent_name)[0]
        nearest_other = other_idx[np.argsort(np.linalg.norm(vectors[other_idx] - centroid, axis=1))][:2]
        near_miss = [{"tweet_id": tweet_ids[i],
                      "reason": f"closest non-member by embedding distance; labelled "
                                f"'{final_labels[i]}' instead"} for i in nearest_other]

        intents.append({
            "id": intent_name, "name": intent_name.replace("_", " ").title(),
            "definition": definition, "include": include, "exclude": exclude,
            "positive_examples": [tweet_ids[i] for i in positive],
            "near_miss_examples": near_miss,
        })

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(yaml.safe_dump({"brand": CHOSEN_BRAND, "intents": intents},
                                        sort_keys=False, allow_unicode=True))
    return final_labels


def _majority_map(raw_labels: np.ndarray, reference: np.ndarray) -> np.ndarray:
    mapped = np.empty_like(reference)
    for cid in np.unique(raw_labels):
        mask = raw_labels == cid
        values, counts = np.unique(reference[mask], return_counts=True)
        mapped[mask] = values[np.argmax(counts)]
    return mapped


def confused_pairs(reference: np.ndarray, mapped: np.ndarray, top_n: int = 3) -> list[tuple]:
    """Where a rerun's majority-mapped labels disagree with the final taxonomy most often --
    the seams BUILD_SPEC.md §5 asks the stability check to name plainly."""
    mismatch = reference != mapped
    counts = Counter(zip(reference[mismatch].tolist(), mapped[mismatch].tolist()))
    return [(a, b, n) for (a, b), n in counts.most_common(top_n)]


def stability_check(vectors: np.ndarray, final_labels: np.ndarray,
                     seeds: list[int] = TAXONOMY_STABILITY_SEEDS,
                     ks: list[int] = TAXONOMY_STABILITY_KS) -> dict:
    """Re-cluster at other seeds/k, map each run onto the final taxonomy by majority vote,
    report Adjusted Rand Index against it, and name the most-confused pair on the least
    stable run (BUILD_SPEC.md §5, taxonomy stability check)."""
    runs = {}
    for seed in seeds:
        for k in ks:
            rerun = cluster(vectors, k=k, seed=seed)
            mapped = _majority_map(rerun, final_labels)
            runs[f"seed{seed}_k{k}"] = {"ari": adjusted_rand_score(final_labels, mapped),
                                         "mapped": mapped}
    worst = min(runs, key=lambda name: runs[name]["ari"])
    return {"ari": {name: r["ari"] for name, r in runs.items()}, "least_stable_run": worst,
            "top_confused_pairs": confused_pairs(final_labels, runs[worst]["mapped"])}


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge clusters into a final taxonomy + stability ARI")
    parser.add_argument("--merge-map", type=Path, required=True,
                         help="YAML: {cluster_id: intent_name, ...}")
    parser.add_argument("--brand", default=CHOSEN_BRAND)
    parser.add_argument("--k", type=int, default=TAXONOMY_KMEANS_K)
    parser.add_argument("--out", type=Path, default=TAXONOMY_DIR / "intents.yaml")
    parser.add_argument("--notes", type=Path, default=None,
                         help="YAML: {intent_name: boundary note to append to exclude}")
    args = parser.parse_args()

    merge_map = {int(k): v for k, v in yaml.safe_load(args.merge_map.read_text()).items()}
    notes = yaml.safe_load(args.notes.read_text()) if args.notes else None
    induced = induce(brand=args.brand, k=args.k)
    final_labels = finalize(induced, merge_map, out_path=args.out, boundary_notes=notes)
    stability = stability_check(induced["vectors"], final_labels)

    console.log(f"Wrote {args.out}.")
    console.log(f"Stability ARI: {stability['ari']}")
    console.log(f"Least stable run: {stability['least_stable_run']}, "
                f"top confused pairs: {stability['top_confused_pairs']}")


if __name__ == "__main__":
    main()
