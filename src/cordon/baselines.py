"""Four baselines through the identical Trace schema as agent.py. BUILD_SPEC.md §9.2.

B0a/B0b bracket the coverage axis (100%/0% coverage, unknown/zero risk) so CORDON's coverage-
at-risk curve has an honest line to beat. B1 is a genuinely different retrieval mechanism
(TF-IDF cosine over the pool, not bge-small) -- a real second system, not a restatement of
CORDON's own index. B2 is one generator call with a complete, fair prompt -- "what most
candidates will submit" -- and beating it honestly is the point of this whole submission.

Runs alone: `python -m cordon.baselines --help`.
"""
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

import numpy as np
from rich.console import Console
from sklearn.metrics.pairwise import cosine_similarity

from config import CHOSEN_BRAND, SEED
from cordon.agent import load_voice, render_taxonomy, sample_test_messages
from cordon.brand_audit import is_deflection
from cordon.linter import lint_draft
from cordon.llm import GEN_MODEL, complete, load_prompt
from cordon.playbook import assign_intents, intent_centroids
from cordon.sampler import load_split_threads, train_weak_classifier
from cordon.schemas import Axes, LinterResult, RetrievedExample, Trace
from cordon.taxonomy import embed
from cordon.verify import claim_check

console = Console()

DEFAULT_AXES = Axes(needs_account_access=False, severity="low", anger=0, contains_pii=False,
                     multi_intent=False)

B2_SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {"type": "string"}, "draft": {"type": "string"},
        "escalate": {"type": "boolean"}, "escalate_reason": {"type": "string"},
    },
    "required": ["intent", "draft", "escalate", "escalate_reason"],
}


def _make_trace(message: str, intent: str, intent_probs: dict, margin: float,
                 retrieved: list[RetrievedExample], reply: str, decision: str,
                 decision_reason: str, evidence_text: str, voice: dict) -> Trace:
    violations = lint_draft(reply, evidence_text, voice)
    cc = claim_check(reply, evidence_text)
    return Trace(message=message, cleaned=message, intent_pred=intent, intent_probs=intent_probs,
                 axes=DEFAULT_AXES, margin=margin, retrieved=retrieved, playbook_used=None,
                 drafts=[reply], draft_final=reply, self_consistency=None,
                 linter=LinterResult(violations=violations), claim_check=cc, risk_score=None,
                 decision=decision, decision_reason=decision_reason, latency_ms=0.0, cost_usd=0.0)


def fit_b0(pool: list) -> tuple[str, str]:
    """Majority intent (nearest-centroid mode over the full pool) + the single most frequent
    real deflection reply (BUILD_SPEC.md §9.2)."""
    vectors = embed([t.first_customer_msg for t in pool])
    intents = assign_intents(vectors, intent_centroids())
    majority_intent = Counter(intents).most_common(1)[0][0]

    deflections = [t.first_agent_reply for t in pool
                   if t.first_agent_reply and is_deflection(t.first_agent_reply)]
    if not deflections:
        raise RuntimeError(f"No deflecting replies found in pool for {CHOSEN_BRAND}.")
    most_common_deflection = Counter(deflections).most_common(1)[0][0]
    return majority_intent, most_common_deflection


def b0a_deflector(message: str, majority_intent: str, deflection_reply: str, voice: dict) -> Trace:
    return _make_trace(message, majority_intent, {majority_intent: 1.0}, 0.0, [], deflection_reply,
                        "auto", "B0a: never escalate (baseline rule, not learned)", "", voice)


def b0b_coward(message: str, majority_intent: str, deflection_reply: str, voice: dict) -> Trace:
    return _make_trace(message, majority_intent, {majority_intent: 1.0}, 0.0, [], deflection_reply,
                        "escalate", "B0b: always escalate (baseline rule, not learned)", "", voice)


def fit_b1(pool: list, calib: list, brand: str = CHOSEN_BRAND) -> dict:
    """TF-IDF + logistic regression for intent; median similarity threshold fit on calib
    (unsupervised -- doesn't need human labels, so nothing here blocks on golden_v1.jsonl)."""
    tfidf, clf = train_weak_classifier(pool, brand)
    pool_matrix = tfidf.transform([t.first_customer_msg for t in pool])
    calib_matrix = tfidf.transform([t.first_customer_msg for t in calib])
    best_sims = cosine_similarity(calib_matrix, pool_matrix).max(axis=1)
    median_sim = float(np.median(best_sims))
    return {"tfidf": tfidf, "clf": clf, "pool": pool, "pool_matrix": pool_matrix,
            "median_sim": median_sim}


def b1_nearest_neighbor(message: str, b1_state: dict, voice: dict) -> Trace:
    tfidf, clf, pool, pool_matrix = (b1_state[k] for k in ("tfidf", "clf", "pool", "pool_matrix"))

    query_vec = tfidf.transform([message])
    probs = clf.predict_proba(query_vec)[0]
    top2 = sorted(probs, reverse=True)[:2]
    margin = float(top2[0] - top2[1]) if len(top2) > 1 else float(top2[0])
    intent = str(clf.classes_[probs.argmax()])
    intent_probs = {str(c): float(p) for c, p in zip(clf.classes_, probs)}

    sims = cosine_similarity(query_vec, pool_matrix).flatten()
    best_idx = int(sims.argmax())
    best_sim = float(sims[best_idx])
    neighbor = pool[best_idx]
    reply = neighbor.first_agent_reply or ""

    decision = "escalate" if best_sim < b1_state["median_sim"] else "auto"
    reason = (f"best_sim {best_sim:.2f} vs. median {b1_state['median_sim']:.2f} "
              f"({'<' if decision == 'escalate' else '>='})")
    retrieved = [RetrievedExample(thread_id=neighbor.thread_id,
                                   customer_message=neighbor.first_customer_msg,
                                   agent_reply=reply, similarity=best_sim)]
    # Evidence = the copied reply itself -- B1 can't hallucinate anything beyond what it copied.
    return _make_trace(message, intent, intent_probs, margin, retrieved, reply, decision, reason,
                        evidence_text=reply, voice=voice)


def b2_obvious_llm(message: str, taxonomy_text: str, brand: str, voice: dict) -> Trace:
    """One generator call, a complete and fair prompt, no retrieval/playbook/voice scaffolding
    -- "what most candidates will submit" (BUILD_SPEC.md §9.2)."""
    prompt = (load_prompt("b2_obvious_llm").replace("{{BRAND}}", brand)
              .replace("{{TAXONOMY}}", taxonomy_text).replace("{{MESSAGE}}", message))
    parsed = complete(prompt, model=GEN_MODEL, schema=B2_SCHEMA).parsed
    reply = parsed["draft"]
    decision = "escalate" if parsed["escalate"] else "auto"
    # No evidence block by design -- B2 has no retrieval/playbook, so any specific claim it
    # makes is, honestly, unsupported by anything external. That gap is the whole point.
    return _make_trace(message, parsed["intent"], {parsed["intent"]: 1.0}, 0.0, [], reply,
                        decision, parsed["escalate_reason"], evidence_text="", voice=voice)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run B0a/B0b/B1/B2 baselines on N demo messages")
    parser.add_argument("--brand", default=CHOSEN_BRAND)
    parser.add_argument("--n", type=int, default=10)
    args = parser.parse_args()

    pool, calib, _ = load_split_threads(args.brand)
    voice = load_voice(args.brand)
    taxonomy_text = render_taxonomy(Path("taxonomy/intents.yaml"))
    messages = sample_test_messages(args.brand, args.n, SEED)

    console.log("Fitting B0a/B0b (majority intent + most common deflection)...")
    majority_intent, deflection_reply = fit_b0(pool)
    console.log(f"majority_intent={majority_intent!r}")
    console.log(f"deflection_reply={deflection_reply!r}")

    console.log("Fitting B1 (TF-IDF + logistic regression, median similarity threshold)...")
    b1_state = fit_b1(pool, calib, args.brand)
    console.log(f"B1 median_sim={b1_state['median_sim']:.3f}")

    for i, message in enumerate(messages, 1):
        console.rule(f"[{i}/{len(messages)}]")
        console.print(f"[bold]message:[/bold] {message}")
        for name, trace in [
            ("B0a Deflector", b0a_deflector(message, majority_intent, deflection_reply, voice)),
            ("B0b Coward", b0b_coward(message, majority_intent, deflection_reply, voice)),
            ("B1 NearestNeighbour", b1_nearest_neighbor(message, b1_state, voice)),
            ("B2 ObviousLLM", b2_obvious_llm(message, taxonomy_text, args.brand, voice)),
        ]:
            console.print(f"  [bold]{name}[/bold] intent={trace.intent_pred} "
                          f"decision={trace.decision} unsup_rate="
                          f"{trace.claim_check.unsupported_claim_rate:.2f} draft={trace.draft_final!r}")


if __name__ == "__main__":
    main()
