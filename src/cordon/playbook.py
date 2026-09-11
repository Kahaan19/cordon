"""Mine per-intent resolution playbooks + a deterministic brand voice profile.
BUILD_SPEC.md §6.2-6.3.

Raw RAG over tweets gives *style* transfer, not *procedure* transfer -- so distill procedure
once, offline, into a readable artifact a reviewer can open directly (docs/DECISION_LOG.md #5).

Pool threads were never individually intent-classified (only the 4,000-message taxonomy sample
was, in Phase 2). Intent assignment here reuses that same deterministic, cached clustering --
nearest-centroid on the embeddings already computed -- rather than spending Phase 4's classifier
budget early on plain corpus labelling.

Runs alone: `python -m cordon.playbook --help`.
"""
from __future__ import annotations

import argparse
import json
import random
import re
from collections import Counter

import numpy as np
import yaml
from rich.console import Console

from config import (
    CHOSEN_BRAND, PLAYBOOK_DIR, PLAYBOOK_REPLIES_PER_INTENT, SEED, TAXONOMY_DIR,
    TAXONOMY_KMEANS_K, VOICE_DIR, VOICE_PROFILE_SAMPLE_SIZE,
)
from cordon.index import load_index
from cordon.llm import GEN_MODEL, complete, load_prompt
from cordon.taxonomy import induce

console = Console()

PLAYBOOK_SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {"type": "string"},
        "typical_steps": {"type": "array", "items": {"type": "string"}},
        "info_agent_requests": {"type": "array", "items": {"type": "string"}},
        "when_they_escalate_to_dm": {"type": "string"},
        "known_links_used": {"type": "array", "items": {"type": "string"}},
        "phrases": {"type": "array", "items": {"type": "string"}},
        "never_promises": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["intent", "typical_steps", "info_agent_requests", "when_they_escalate_to_dm",
                 "known_links_used", "phrases", "never_promises"],
}

SIGNOFF_RE = re.compile(r"\^[A-Z]{1,3}\b")
APOLOGY_RE = re.compile(r"^(sorry|we'?re sorry|i'?m sorry|apologies|apologize)", re.IGNORECASE)
GREETING_NAME_RE = re.compile(r"^(hi|hey|hello|hiya)[,]?\s+[A-Z][a-z]+\b", re.IGNORECASE)
EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U00002190-\U000021FF\U00002B00-\U00002BFF]"
)


def intent_centroids(brand: str = CHOSEN_BRAND, k: int = TAXONOMY_KMEANS_K,
                      seed: int = SEED) -> dict[str, np.ndarray]:
    """Reuses the deterministic, cached taxonomy induction -- zero new LLM calls."""
    induced = induce(brand=brand, k=k, seed=seed)
    merge_map = {int(cid): name for cid, name in
                 yaml.safe_load((TAXONOMY_DIR / "merge_map.yaml").read_text()).items()}
    final_labels = np.array([merge_map[label] for label in induced["labels"]])
    return {name: induced["vectors"][final_labels == name].mean(axis=0)
            for name in set(final_labels) if name != "other"}


def assign_intents(vectors: np.ndarray, centroids: dict[str, np.ndarray]) -> np.ndarray:
    names = list(centroids)
    sims = vectors @ np.stack([centroids[n] for n in names]).T
    return np.array([names[i] for i in sims.argmax(axis=1)])


def mine_playbook(brand: str, intent: str, replies: list[str]) -> dict:
    prompt = (load_prompt("playbook_mine")
              .replace("{{BRAND}}", brand).replace("{{INTENT}}", intent)
              .replace("{{REPLIES}}", "\n".join(f"- {r}" for r in replies)))
    return complete(prompt, model=GEN_MODEL, schema=PLAYBOOK_SCHEMA).parsed


def voice_profile(replies: list[str]) -> dict:
    """Deterministic stats -- checkable, not a vibe (BUILD_SPEC.md §6.3)."""
    n = len(replies)
    signoffs = [m.group() for r in replies if (m := SIGNOFF_RE.search(r))]
    top_signoff = Counter(signoffs).most_common(1)
    return {
        "n_replies": n,
        "mean_length": float(np.mean([len(r) for r in replies])),
        "exclamation_rate": sum("!" in r for r in replies) / n,
        "emoji_rate": sum(bool(EMOJI_RE.search(r)) for r in replies) / n,
        "apology_opener_rate": sum(bool(APOLOGY_RE.match(r.strip())) for r in replies) / n,
        "signoff_rate": len(signoffs) / n,
        "top_signoff": top_signoff[0][0] if top_signoff else None,
        "uses_customer_name_rate": sum(bool(GREETING_NAME_RE.match(r.strip())) for r in replies) / n,
        "question_per_reply_rate": sum("?" in r for r in replies) / n,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Mine per-intent playbooks + a voice profile")
    parser.add_argument("--brand", default=CHOSEN_BRAND)
    parser.add_argument("--n-per-intent", type=int, default=PLAYBOOK_REPLIES_PER_INTENT)
    parser.add_argument("--n-voice", type=int, default=VOICE_PROFILE_SAMPLE_SIZE)
    parser.add_argument("--only-intent", default=None,
                         help="mine just this one intent and skip the voice profile (preview)")
    args = parser.parse_args()

    index = load_index(args.brand)
    centroids = intent_centroids(args.brand)
    intents = assign_intents(index["vectors"], centroids)

    # DECISION: each intent (and the voice sample) gets its own stable seed derived from its
    # name, not one shared stream consumed in loop order -- so `--only-intent X` standalone
    # reproduces byte-identical output to X's slot inside the full run.
    target_intents = [args.only_intent] if args.only_intent else sorted(centroids)
    PLAYBOOK_DIR.mkdir(parents=True, exist_ok=True)
    for intent in target_intents:
        idx = np.where(intents == intent)[0]
        replies = index["meta"].iloc[idx]["substantive_agent_reply"].tolist()
        sample = random.Random(f"{SEED}-{intent}").sample(replies, min(args.n_per_intent, len(replies)))
        playbook = mine_playbook(args.brand, intent, sample)
        (PLAYBOOK_DIR / f"{intent}.json").write_text(json.dumps(playbook, indent=2))
        console.log(f"{intent}: mined from {len(sample)} replies -> {PLAYBOOK_DIR}/{intent}.json")

    if args.only_intent:
        return

    all_replies = index["meta"]["substantive_agent_reply"].tolist()
    voice_sample = random.Random(f"{SEED}-voice").sample(all_replies, min(args.n_voice, len(all_replies)))
    VOICE_DIR.mkdir(parents=True, exist_ok=True)
    (VOICE_DIR / f"{args.brand}.json").write_text(json.dumps(voice_profile(voice_sample), indent=2))
    console.log(f"Voice profile written from {len(voice_sample)} replies -> "
                f"{VOICE_DIR}/{args.brand}.json")


if __name__ == "__main__":
    main()
