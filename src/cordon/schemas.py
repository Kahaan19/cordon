"""Pydantic models shared across phases.

`Trace` (BUILD_SPEC.md §7) is added now that Phase 4 needs it. `GoldenItem`/`JudgeScore`
(BUILD_SPEC.md §9) still belong to Phase 6 and aren't stubbed ahead of need.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class Turn(BaseModel):
    role: Literal["customer", "agent"]
    text: str
    created_at: datetime
    tweet_id: str


class Thread(BaseModel):
    thread_id: str
    brand: str
    turns: list[Turn]
    n_turns: int
    n_branches: int
    first_customer_msg: str
    first_agent_reply: str | None
    last_customer_msg: str
    created_at_root: datetime


class Axes(BaseModel):
    needs_account_access: bool
    severity: Literal["low", "med", "high"]
    anger: Literal[0, 1, 2]
    contains_pii: bool
    multi_intent: bool


class RetrievedExample(BaseModel):
    thread_id: str
    customer_message: str
    agent_reply: str
    similarity: float


class LinterResult(BaseModel):
    violations: list[str]


class ClaimVerdict(BaseModel):
    claim: str
    verdict: Literal["supported", "unsupported", "irrelevant"]


class ClaimCheck(BaseModel):
    claims: list[ClaimVerdict]
    unsupported_claim_rate: float


class SelfConsistency(BaseModel):
    drafts: list[str]
    mean_pairwise_cosine: float


class RiskScore(BaseModel):
    """DECISION: features are real; weights are a hand-set placeholder until Phase 6b fits a
    logistic regression on calib-split human labels (BUILD_SPEC.md §7.4). See
    docs/DECISION_LOG.md."""
    features: dict[str, float]
    score: float
    weights_source: Literal["placeholder", "fitted"] = "placeholder"


class Trace(BaseModel):
    message: str
    cleaned: str
    intent_pred: str
    intent_probs: dict[str, float]
    axes: Axes
    margin: float
    retrieved: list[RetrievedExample]
    playbook_used: str | None
    drafts: list[str]
    draft_final: str | None
    self_consistency: SelfConsistency | None
    linter: LinterResult | None
    claim_check: ClaimCheck | None
    risk_score: RiskScore | None
    decision: Literal["auto", "escalate"]
    decision_reason: str
    latency_ms: float
    cost_usd: float
