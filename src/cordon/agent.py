"""The agent: classify -> retrieve -> draft -> verify -> decide, into one Trace. BUILD_SPEC.md §7.

Every step is logged onto a single Trace object -- the trace viewer (Phase 7) renders it, the
evaluator (Phase 6) consumes it, the judge scores it. Deterministic checks live in linter.py;
claim-check/self-consistency/risk-score/hard-overrides live in verify.py; this module is the
pipeline that calls all of them in order.

Runs alone: `python -m cordon.agent --help`.
"""
from __future__ import annotations

import argparse
import json
import random
import time
from pathlib import Path

import yaml
from rich.console import Console

from config import (
    CHOSEN_BRAND, DRAFT_TEMPERATURE, INTERIM_DIR, PLAYBOOK_DIR, SELF_CONSISTENCY_SALTS, SEED,
    VOICE_DIR, time_split,
)
from cordon.index import load_index, mmr_diversify, search
from cordon.ingest import clean_text
from cordon.linter import lint_draft
from cordon.llm import GEN_MODEL, complete, load_prompt
from cordon.schemas import Axes, LinterResult, RetrievedExample, Thread, Trace
from cordon.taxonomy import embed
from cordon.verify import (
    check_claim_override, check_hard_overrides, claim_check, compute_risk_score, decide,
    self_consistency,
)

console = Console()

CLASSIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {"type": "string"}, "runner_up": {"type": "string"},
        "confidence": {"type": "number"}, "runner_up_confidence": {"type": "number"},
        "needs_account_access": {"type": "boolean"},
        "severity": {"type": "string", "enum": ["low", "med", "high"]},
        "anger": {"type": "integer"},  # DECISION: Gemini's structured-output enum only accepts
        # string values -- an integer enum here caused a schema validation error on every call.
        # Pydantic's Axes(anger: Literal[0,1,2]) is the real gate; a bad value still retries/
        # falls back to "other" (docs/DECISION_LOG.md).
        "contains_pii": {"type": "boolean"}, "multi_intent": {"type": "boolean"},
    },
    "required": ["intent", "runner_up", "confidence", "runner_up_confidence",
                 "needs_account_access", "severity", "anger", "contains_pii", "multi_intent"],
}


def render_taxonomy(taxonomy_path: Path) -> str:
    data = yaml.safe_load(taxonomy_path.read_text())
    return "\n\n".join(
        f"id: {i['id']}\ndefinition: {i['definition']}\ninclude: {i['include']}\nexclude: {i['exclude']}"
        for i in data["intents"]
    )


def classify(message: str, taxonomy_text: str, brand: str) -> tuple[str, str, float, float, Axes]:
    """BUILD_SPEC.md §7.1: force JSON, validate with pydantic, retry once, fall back to other."""
    prompt = (load_prompt("classify").replace("{{BRAND}}", brand)
              .replace("{{TAXONOMY}}", taxonomy_text).replace("{{MESSAGE}}", message))
    for attempt in range(2):
        try:
            parsed = complete(prompt, model=GEN_MODEL, schema=CLASSIFY_SCHEMA, cache=(attempt == 0)).parsed
            axes = Axes(needs_account_access=parsed["needs_account_access"], severity=parsed["severity"],
                        anger=parsed["anger"], contains_pii=parsed["contains_pii"],
                        multi_intent=parsed["multi_intent"])
            return (parsed["intent"], parsed["runner_up"], float(parsed["confidence"]),
                    float(parsed["runner_up_confidence"]), axes)
        except Exception as exc:
            console.log(f"[yellow]Classify parse failed (attempt {attempt + 1}/2): {exc}[/yellow]")
    fallback_axes = Axes(needs_account_access=False, severity="low", anger=0, contains_pii=False,
                          multi_intent=False)
    return "other", "other", 0.0, 0.0, fallback_axes


def retrieve(message: str, index: dict, top_k: int = 8, mmr_k: int = 3) -> list[RetrievedExample]:
    """BUILD_SPEC.md §6.1: top-8 then MMR-diversify to 3, reusing index.py exactly."""
    query_vector = embed([message])[0]
    raw = search(query_vector, index["vectors"], k=top_k)
    diversified = mmr_diversify(query_vector, index["vectors"], raw, k=mmr_k)
    meta = index["meta"]
    return [RetrievedExample(
        thread_id=meta.iloc[i]["thread_id"], customer_message=meta.iloc[i]["first_customer_msg"],
        agent_reply=meta.iloc[i]["substantive_agent_reply"], similarity=float(index["vectors"][i] @ query_vector),
    ) for i in diversified]


def load_playbook(intent: str) -> dict | None:
    path = PLAYBOOK_DIR / f"{intent}.json"
    return json.loads(path.read_text()) if path.exists() else None


def load_voice(brand: str = CHOSEN_BRAND) -> dict:
    return json.loads((VOICE_DIR / f"{brand}.json").read_text())


def build_evidence_text(playbook: dict | None, retrieved: list[RetrievedExample]) -> str:
    parts = []
    if playbook:
        parts.append(f"Known links: {playbook.get('known_links_used')}")
        parts.append(f"Typical steps: {playbook.get('typical_steps')}")
        parts.append(f"Never promise: {playbook.get('never_promises')}")
    parts += [f"Past reply: {r.agent_reply}" for r in retrieved]
    return "\n".join(parts)


def draft(message: str, intent: str, playbook: dict | None, retrieved: list[RetrievedExample],
          voice: dict, brand: str, salt: str) -> str:
    """BUILD_SPEC.md §7.2. `salt` gives each self-consistency sample its own cache key without
    touching llm.py's cache-key formula (docs/DECISION_LOG.md)."""
    exemplars = "\n".join(f"Customer: {r.customer_message}\nAgent: {r.agent_reply}" for r in retrieved)
    prompt = (load_prompt("draft").replace("{{BRAND}}", brand).replace("{{MESSAGE}}", message)
              .replace("{{INTENT}}", intent).replace("{{PLAYBOOK}}", json.dumps(playbook or {}))
              .replace("{{EXEMPLARS}}", exemplars).replace("{{VOICE}}", json.dumps(voice)))
    if salt:
        prompt += f"\n\n<!-- {salt} -->"
    return complete(prompt, model=GEN_MODEL, temperature=DRAFT_TEMPERATURE, schema=None).text.strip()


def run_agent(message: str, index: dict, taxonomy_text: str, brand: str = CHOSEN_BRAND) -> Trace:
    start = time.perf_counter()
    cleaned, _ = clean_text(message)
    override_reason = check_hard_overrides(message)

    intent, runner_up, confidence, runner_up_conf, axes = classify(cleaned, taxonomy_text, brand)
    margin = confidence - runner_up_conf
    intent_probs = {intent: confidence, runner_up: runner_up_conf}

    if override_reason:
        decision, decision_reason = decide(risk_score=1.0, override_reason=override_reason)
        return Trace(message=message, cleaned=cleaned, intent_pred=intent, intent_probs=intent_probs,
                     axes=axes, margin=margin, retrieved=[], playbook_used=None, drafts=[],
                     draft_final=None, self_consistency=None, linter=None, claim_check=None,
                     risk_score=None, decision=decision, decision_reason=decision_reason,
                     latency_ms=(time.perf_counter() - start) * 1000, cost_usd=0.0)

    retrieved = retrieve(cleaned, index)
    playbook = load_playbook(intent)
    voice = load_voice(brand)
    evidence_text = build_evidence_text(playbook, retrieved)

    drafts = [draft(cleaned, intent, playbook, retrieved, voice, brand, salt)
              for salt in SELF_CONSISTENCY_SALTS]
    draft_final = drafts[0]

    sc = self_consistency(drafts)
    linter_result = LinterResult(violations=lint_draft(draft_final, evidence_text, voice))
    cc = claim_check(draft_final, evidence_text)
    max_retrieval_sim = max((r.similarity for r in retrieved), default=0.0)

    risk = compute_risk_score(margin, max_retrieval_sim, sc.mean_pairwise_cosine,
                               axes.needs_account_access, len(linter_result.violations),
                               cc.unsupported_claim_rate, axes.anger, axes.severity)
    claim_override_reason = check_claim_override(cc.unsupported_claim_rate)
    decision, decision_reason = decide(risk.score, override_reason=claim_override_reason)

    return Trace(message=message, cleaned=cleaned, intent_pred=intent, intent_probs=intent_probs,
                 axes=axes, margin=margin, retrieved=retrieved,
                 playbook_used=(playbook.get("intent") if playbook else None), drafts=drafts,
                 draft_final=draft_final, self_consistency=sc, linter=linter_result, claim_check=cc,
                 risk_score=risk, decision=decision, decision_reason=decision_reason,
                 latency_ms=(time.perf_counter() - start) * 1000, cost_usd=0.0)


def sample_test_messages(brand: str, n: int, seed: int) -> list[str]:
    """10 demo messages from the calib split -- never golden or pool, so a print-traces smoke
    test can't be confused with evaluation or data leakage."""
    threads = [Thread.model_validate_json(line)
               for line in open(INTERIM_DIR / f"threads_{brand}.jsonl")]
    _, calib, _ = time_split(threads, time_key=lambda t: t.created_at_root)
    chosen = random.Random(seed).sample(calib, min(n, len(calib)))
    return [t.first_customer_msg for t in chosen]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the agent on N demo messages, print traces")
    parser.add_argument("--brand", default=CHOSEN_BRAND)
    parser.add_argument("--n", type=int, default=10)
    args = parser.parse_args()

    index = load_index(args.brand)
    taxonomy_text = render_taxonomy(Path("taxonomy/intents.yaml"))
    messages = sample_test_messages(args.brand, args.n, SEED)

    for i, message in enumerate(messages, 1):
        trace = run_agent(message, index, taxonomy_text, args.brand)
        console.rule(f"[{i}/{len(messages)}]")
        console.print(trace.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
