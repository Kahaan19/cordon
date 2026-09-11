"""Retrieval index over the pool corpus. BUILD_SPEC.md §6.1.

Corpus = pool threads with >=1 substantive agent turn -- excluding deflection-only threads is
deliberate: you cannot ground a resolution in a corpus of non-resolutions (docs/DECISION_LOG.md
#4). Embed the first customer message; search is a plain numpy dot product over normalised
vectors (cosine similarity) -- no FAISS.

Runs alone: `python -m cordon.index --help`.
"""
from __future__ import annotations

import argparse
import random

import numpy as np
import pandas as pd
from rich.console import Console

from config import (
    CACHE_DIR, CHOSEN_BRAND, INTERIM_DIR, REPORT_DIR, RETRIEVAL_DIVERSITY_SAMPLE_SIZE,
    RETRIEVAL_MMR_K, RETRIEVAL_MMR_LAMBDA, RETRIEVAL_TOP_K, SEED, time_split,
)
from cordon.brand_audit import is_substantive
from cordon.schemas import Thread
from cordon.taxonomy import embed

console = Console()


def load_pool_threads(brand: str) -> list[Thread]:
    path = INTERIM_DIR / f"threads_{brand}.jsonl"
    threads = [Thread.model_validate_json(line) for line in open(path)]
    pool, _, _ = time_split(threads, time_key=lambda t: t.created_at_root)
    return pool


def substantive_agent_reply(thread: Thread) -> str | None:
    return next((t.text for t in thread.turns if t.role == "agent" and is_substantive(t.text)), None)


def build_index(brand: str = CHOSEN_BRAND) -> dict:
    pool = load_pool_threads(brand)
    corpus = [(t, r) for t in pool if (r := substantive_agent_reply(t)) is not None]

    texts = [t.first_customer_msg for t, _ in corpus]
    vectors = embed(texts)
    meta = pd.DataFrame({
        "thread_id": [t.thread_id for t, _ in corpus],
        "first_customer_msg": texts,
        "substantive_agent_reply": [r for _, r in corpus],
    })
    return {"vectors": vectors, "meta": meta}


def save_index(index: dict, brand: str = CHOSEN_BRAND) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    np.save(CACHE_DIR / f"embeddings_{brand}.npy", index["vectors"])
    index["meta"].to_parquet(CACHE_DIR / f"metadata_{brand}.parquet")


def load_index(brand: str = CHOSEN_BRAND) -> dict:
    vectors = np.load(CACHE_DIR / f"embeddings_{brand}.npy")
    meta = pd.read_parquet(CACHE_DIR / f"metadata_{brand}.parquet")
    return {"vectors": vectors, "meta": meta}


def search(query_vector: np.ndarray, vectors: np.ndarray, k: int) -> np.ndarray:
    sims = vectors @ query_vector
    return np.argsort(-sims)[:k]


def mmr_diversify(query_vector: np.ndarray, vectors: np.ndarray, candidate_idx: np.ndarray,
                   k: int = RETRIEVAL_MMR_K, lam: float = RETRIEVAL_MMR_LAMBDA) -> np.ndarray:
    """Maximal Marginal Relevance: greedily pick argmax(lam*relevance - (1-lam)*redundancy)."""
    selected: list[int] = []
    pool = list(candidate_idx)
    while pool and len(selected) < k:
        def score(i):
            relevance = float(vectors[i] @ query_vector)
            redundancy = max((float(vectors[i] @ vectors[j]) for j in selected), default=0.0)
            return lam * relevance - (1 - lam) * redundancy
        best = max(pool, key=score)
        selected.append(best)
        pool.remove(best)
    return np.array(selected)


def mean_pairwise_similarity(vectors: np.ndarray, idx: np.ndarray) -> float:
    if len(idx) < 2:
        return 0.0
    sims = vectors[idx] @ vectors[idx].T
    n = len(idx)
    return float((sims.sum() - n) / (n * (n - 1)))  # exclude the diagonal (self-similarity = 1)


def duplication_report(vectors: np.ndarray, query_idx: list[int]) -> dict:
    """Report the raw-top-8 vs. MMR-diversified-top-3 duplication rate (BUILD_SPEC.md §6.1)."""
    before, after = [], []
    for qi in query_idx:
        query_vector = vectors[qi]
        raw = search(query_vector, vectors, k=RETRIEVAL_TOP_K + 1)
        raw = raw[raw != qi][:RETRIEVAL_TOP_K]
        diversified = mmr_diversify(query_vector, vectors, raw)
        before.append(mean_pairwise_similarity(vectors, raw))
        after.append(mean_pairwise_similarity(vectors, diversified))
    return {"n_queries": len(query_idx), "mean_pairwise_sim_top8_raw": float(np.mean(before)),
            "mean_pairwise_sim_top3_mmr": float(np.mean(after))}


def write_diversity_report(report: dict, out_path=REPORT_DIR / "retrieval_diversity.md") -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        "# Retrieval diversity: raw top-k vs. MMR\n\n"
        f"Sampled {report['n_queries']} queries from the pool corpus.\n\n"
        f"- Mean pairwise cosine similarity, raw top-{RETRIEVAL_TOP_K}: "
        f"{report['mean_pairwise_sim_top8_raw']:.3f}\n"
        f"- Mean pairwise cosine similarity, MMR-diversified top-{RETRIEVAL_MMR_K} "
        f"(λ={RETRIEVAL_MMR_LAMBDA}): {report['mean_pairwise_sim_top3_mmr']:.3f}\n\n"
        "Lower is more diverse. The raw top-k for this corpus tends to be near-copies of the "
        "same generic thread; MMR trades a little pure relevance for materially less redundant "
        "exemplars.\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the pool retrieval index + diversity report")
    parser.add_argument("--brand", default=CHOSEN_BRAND)
    parser.add_argument("--sample-queries", type=int, default=RETRIEVAL_DIVERSITY_SAMPLE_SIZE)
    args = parser.parse_args()

    index = build_index(args.brand)
    save_index(index, args.brand)
    console.log(f"Indexed {len(index['meta'])} substantive threads for {args.brand}.")

    rng = random.Random(SEED)
    query_idx = rng.sample(range(len(index["meta"])), min(args.sample_queries, len(index["meta"])))
    report = duplication_report(index["vectors"], query_idx)
    write_diversity_report(report)
    console.log(f"Diversity report: {report}")


if __name__ == "__main__":
    main()
