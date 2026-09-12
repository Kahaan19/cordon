"""Claim-support check, self-consistency, risk score, and hard overrides. BUILD_SPEC.md §7.3(b),
§7.3(c), §7.4.

Claim extraction is a cheap sentence-split, not an LLM call (docs/DECISION_LOG.md #29's call-
volume budget) -- only the supported/unsupported/irrelevant verdict goes to the judge (Ollama,
free, unlimited). Hard overrides reuse the same regexes that make an item redteam/hard-worthy
for golden-set sampling (cordon.sampler) -- the same patterns that justify human review there
justify a forced escalation here.
"""
from __future__ import annotations

import re

import numpy as np

from config import (
    RISK_DECISION_THRESHOLD_PLACEHOLDER, RISK_MAX_LINTER_VIOLATIONS_FOR_NORMALIZATION,
    RISK_PLACEHOLDER_WEIGHTS, UNSUPPORTED_CLAIM_OVERRIDE_THRESHOLD,
)
from cordon.index import mean_pairwise_similarity
from cordon.llm import JUDGE_MODEL, complete, load_prompt
from cordon.sampler import HARD_PATTERNS, REDTEAM_PATTERNS
from cordon.schemas import ClaimCheck, ClaimVerdict, RiskScore, SelfConsistency
from cordon.taxonomy import embed

CLAIM_SCHEMA = {
    "type": "object",
    "properties": {"verdict": {"type": "string", "enum": ["supported", "unsupported", "irrelevant"]}},
    "required": ["verdict"],
}

SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def extract_claims(draft: str) -> list[str]:
    """DECISION: drop questions -- a question has no truth value for evidence to support or
    contradict, and letting the judge score them anyway produced genuinely inconsistent
    verdicts on identical phrasing across calls (e.g. "Which device do you use?" scored
    supported in one trace, unsupported in another). Commitment phrases ("we'll share your
    feedback") are kept and correctly scored unsupported when ungrounded -- that's a real,
    useful catch this check is designed to make, not noise. See docs/DECISION_LOG.md."""
    sentences = [s.strip() for s in SENTENCE_SPLIT_RE.split(draft.strip()) if len(s.strip()) > 8]
    return [s for s in sentences if not s.endswith("?")]


def check_claim(evidence: str, claim: str) -> str:
    prompt = load_prompt("claim_check").replace("{{EVIDENCE}}", evidence).replace("{{CLAIM}}", claim)
    return complete(prompt, model=JUDGE_MODEL, provider="ollama", schema=CLAIM_SCHEMA).parsed["verdict"]


def claim_check(draft: str, evidence_text: str) -> ClaimCheck:
    claims = extract_claims(draft)
    verdicts = [ClaimVerdict(claim=c, verdict=check_claim(evidence_text, c)) for c in claims]
    checkable = [v for v in verdicts if v.verdict != "irrelevant"]
    unsupported = [v for v in checkable if v.verdict == "unsupported"]
    rate = len(unsupported) / len(checkable) if checkable else 0.0
    return ClaimCheck(claims=verdicts, unsupported_claim_rate=rate)


def self_consistency(drafts: list[str]) -> SelfConsistency:
    """Mean pairwise cosine of 3 T=0.7 draft samples -- low agreement is an escalation signal
    with no logprobs required (BUILD_SPEC.md §7.3(c))."""
    vectors = embed(drafts)
    mean_sim = mean_pairwise_similarity(vectors, np.arange(len(drafts)))
    return SelfConsistency(drafts=drafts, mean_pairwise_cosine=mean_sim)


def compute_risk_score(margin: float, max_retrieval_sim: float, self_consistency_score: float,
                        needs_account_access: bool, n_linter_violations: int,
                        unsupported_claim_rate: float, anger: int, severity: str) -> RiskScore:
    """BUILD_SPEC.md §7.4. Phase 5 (calibrate.py) fits real logistic-regression coefficients on
    top of this feature computation -- it replaces RISK_PLACEHOLDER_WEIGHTS and the decision
    threshold below, not this function's features, which are already real. The hard overrides
    in this module (check_hard_overrides, check_claim_override) sit outside that fit entirely
    and are never learned, on either side of the placeholder-vs-fitted line."""
    severity_value = {"low": 0.0, "med": 0.5, "high": 1.0}[severity]
    features = {
        "margin_uncertainty": 1 - max(0.0, min(1.0, margin)),
        "retrieval_uncertainty": 1 - max(0.0, min(1.0, max_retrieval_sim)),
        "consistency_uncertainty": 1 - max(0.0, min(1.0, self_consistency_score)),
        "needs_account_access": float(needs_account_access),
        "linter_violations": min(1.0, n_linter_violations / RISK_MAX_LINTER_VIOLATIONS_FOR_NORMALIZATION),
        "unsupported_claims": unsupported_claim_rate,
        "anger_severity": (anger / 2 + severity_value) / 2,
    }
    score = sum(RISK_PLACEHOLDER_WEIGHTS[k] * v for k, v in features.items())
    return RiskScore(features=features, score=score, weights_source="placeholder")


def check_hard_overrides(message: str) -> str | None:
    """Message-level hard overrides -- checked before drafting even starts, so the agent never
    drafts a reply to a self-harm message. Never learned, always applied (BUILD_SPEC.md §7.4).
    See check_claim_override for the one hard override that can only fire after drafting."""
    if REDTEAM_PATTERNS["self_harm"].search(message):
        return "hard_override: self-harm/crisis language in message"
    if HARD_PATTERNS["legal_terms"].search(message):
        return "hard_override: legal/regulatory language in message"
    if REDTEAM_PATTERNS["pii"].search(message):
        return "hard_override: PII detected in message"
    if REDTEAM_PATTERNS["prompt_injection"].search(message):
        return "hard_override: prompt-injection phrasing in message"
    return None


def check_claim_override(unsupported_claim_rate: float) -> str | None:
    """The one hard override that depends on the draft, not the message -- can only be checked
    after claim_check() runs. Same asymmetric-cost logic as check_hard_overrides: a real trace
    with unsupported_claim_rate=1.00 scored risk=0.23 under the placeholder weights (0.15 max
    contribution from this feature alone) and would have auto-sent a near-fully-ungrounded
    draft. See docs/DECISION_LOG.md #41."""
    if unsupported_claim_rate >= UNSUPPORTED_CLAIM_OVERRIDE_THRESHOLD:
        return (f"hard_override: unsupported_claim_rate {unsupported_claim_rate:.2f} >= "
                f"{UNSUPPORTED_CLAIM_OVERRIDE_THRESHOLD}")
    return None


def decide(risk_score: float, override_reason: str | None) -> tuple[str, str]:
    if override_reason:
        return "escalate", override_reason
    if risk_score > RISK_DECISION_THRESHOLD_PLACEHOLDER:
        return "escalate", f"risk_score {risk_score:.2f} > placeholder threshold {RISK_DECISION_THRESHOLD_PLACEHOLDER}"
    return "auto", f"risk_score {risk_score:.2f} <= placeholder threshold {RISK_DECISION_THRESHOLD_PLACEHOLDER}"
