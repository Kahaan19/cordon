"""Induce raw clusters from data. BUILD_SPEC.md §5 steps 1-4.

Sample, embed, KMeans(k=30, seed=0), name each cluster via the LLM, print a table. Merging
clusters into a final taxonomy is a human judgement call, handled separately in
`taxonomy_finalize.py` once you've reviewed this table.

Runs alone: `python -m cordon.taxonomy --help`.
"""
from __future__ import annotations

import argparse
import random

import numpy as np
from rich.console import Console
from sklearn.cluster import KMeans

from config import (
    BGE_MODEL_NAME, BGE_QUERY_PREFIX, CHOSEN_BRAND, INTERIM_DIR, SEED, TAXONOMY_KMEANS_K,
    TAXONOMY_SAMPLE_SIZE, time_split,
)
from cordon.llm import GEN_MODEL, complete, load_prompt
from cordon.schemas import Thread

console = Console()

CLUSTER_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "one_line_definition": {"type": "string"},
        "inclusion_criteria": {"type": "string"},
        "exclusion_criteria": {"type": "string"},
        "is_junk": {"type": "boolean"},
    },
    "required": ["name", "one_line_definition", "inclusion_criteria", "exclusion_criteria", "is_junk"],
}

_MODEL = None


def _get_embedding_model():
    global _MODEL
    if _MODEL is None:
        import torch
        from sentence_transformers import SentenceTransformer
        device = "mps" if torch.backends.mps.is_available() else "cpu"
        _MODEL = SentenceTransformer(BGE_MODEL_NAME, device=device)
    return _MODEL


def embed(texts: list[str]) -> np.ndarray:
    """BAAI/bge-small-en-v1.5, with the model card's query instruction prefix (CITATIONS.md)."""
    model = _get_embedding_model()
    prefixed = [BGE_QUERY_PREFIX + t for t in texts]
    return np.asarray(model.encode(prefixed, normalize_embeddings=True, show_progress_bar=False))


def load_pool_first_messages(brand: str) -> list[tuple[str, str]]:
    """(tweet_id, cleaned text) of the first customer message per thread, pool split only."""
    path = INTERIM_DIR / f"threads_{brand}.jsonl"
    threads = [Thread.model_validate_json(line) for line in open(path)]
    pool, _, _ = time_split(threads, time_key=lambda t: t.created_at_root)
    return [(t.turns[0].tweet_id, t.first_customer_msg) for t in pool]


def sample_messages(messages: list[tuple[str, str]], n: int, seed: int) -> list[tuple[str, str]]:
    if len(messages) <= n:
        return messages
    return random.Random(seed).sample(messages, n)


def cluster(vectors: np.ndarray, k: int, seed: int) -> np.ndarray:
    return KMeans(n_clusters=k, random_state=seed, n_init=10).fit_predict(vectors)


def pick_cluster_examples(vectors: np.ndarray, labels: np.ndarray, texts: list[str],
                           cluster_id: int, seed: int) -> list[str]:
    """12 closest to centroid + 3 random members (BUILD_SPEC.md §5 step 4)."""
    idx = np.where(labels == cluster_id)[0]
    centroid = vectors[idx].mean(axis=0)
    order = idx[np.argsort(np.linalg.norm(vectors[idx] - centroid, axis=1))]
    core = list(order[:12])
    remaining = [i for i in idx if i not in set(core)]
    extra = random.Random(seed + cluster_id).sample(remaining, min(3, len(remaining)))
    return [texts[i] for i in core + extra]


def describe_cluster(brand: str, examples: list[str]) -> dict:
    prompt = (load_prompt("cluster_describe")
              .replace("{{BRAND}}", brand)
              .replace("{{EXAMPLES}}", "\n".join(f"- {e}" for e in examples)))
    return complete(prompt, model=GEN_MODEL, schema=CLUSTER_SCHEMA).parsed


def induce(brand: str = CHOSEN_BRAND, k: int = TAXONOMY_KMEANS_K, seed: int = SEED,
           sample_size: int = TAXONOMY_SAMPLE_SIZE) -> dict:
    sample = sample_messages(load_pool_first_messages(brand), sample_size, seed)
    tweet_ids, texts = [t for t, _ in sample], [m for _, m in sample]
    vectors = embed(texts)
    labels = cluster(vectors, k, seed)

    clusters = []
    for cid in range(k):
        examples = pick_cluster_examples(vectors, labels, texts, cid, seed)
        desc = describe_cluster(brand, examples)
        clusters.append({"cluster_id": cid, "size": int((labels == cid).sum()), **desc})

    return {"tweet_ids": tweet_ids, "texts": texts, "vectors": vectors, "labels": labels,
            "clusters": clusters}


def print_cluster_table(clusters: list[dict]) -> None:
    for c in sorted(clusters, key=lambda c: -c["size"]):
        flag = " [red][JUNK][/red]" if c.get("is_junk") else ""
        console.print(f"[{c['cluster_id']:>2}] n={c['size']:<5} {c['name']}{flag} "
                      f"— {c['one_line_definition']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Sample + embed + cluster + name; print a table")
    parser.add_argument("--brand", default=CHOSEN_BRAND)
    parser.add_argument("--k", type=int, default=TAXONOMY_KMEANS_K)
    args = parser.parse_args()
    induced = induce(brand=args.brand, k=args.k)
    print_cluster_table(induced["clusters"])


if __name__ == "__main__":
    main()
