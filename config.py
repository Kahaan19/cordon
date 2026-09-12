"""All constants, seeds, model IDs, thresholds, and paths for cordon. Nothing here calls a model
or touches disk beyond resolving paths — every other module imports from here rather than
re-declaring a seed, a path, or a regex.
"""
from __future__ import annotations

from pathlib import Path

SEED = 0

# --- paths -------------------------------------------------------------
ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
INTERIM_DIR = DATA_DIR / "interim"
GOLDEN_DIR = DATA_DIR / "golden"
CACHE_DIR = DATA_DIR / "cache"
SAMPLE_DIR = DATA_DIR / "sample"
REPORT_DIR = ROOT / "report"
TAXONOMY_DIR = ROOT / "taxonomy"
PLAYBOOK_DIR = ROOT / "playbooks"
VOICE_DIR = ROOT / "voice"

RAW_CSV_PATH = RAW_DIR / "twcs.csv"
LLM_CACHE_PATH = CACHE_DIR / "llm_cache.sqlite"

# --- models --------------------------------------------------------------
# DECISION: gemini-flash-latest now resolves to gemini-3.8-flash, a newest-tier flagship preview
# whose free tier is a 20-requests-PER-DAY cap (confirmed live via a 429 RESOURCE_EXHAUSTED
# error naming that exact quota) -- not viable for a ~30-call taxonomy induction, let alone the
# rest of the pipeline. gemini-2.5-flash/-flash-lite are fully retired (404 for new users).
# gemini-3.5-flash-lite is live and current; picked as the lighter, still-"Flash"-family tier
# most likely to carry a real free daily quota. Re-verify before a long run -- free-tier model
# IDs and limits move. See docs/DECISION_LOG.md #23.
GEN_MODEL = "gemini-3.5-flash-lite"
JUDGE_MODEL = "qwen3:8b"
OLLAMA_HOST_DEFAULT = "http://localhost:11434"

# --- time-based split ----------------------------------------------------
# DECISION: never train_test_split(shuffle=True) on this corpus — near-duplicate threads about
# the same incident hours apart leak across a random split. See BUILD_SPEC.md §3.
POOL_FRAC = 0.70
CALIB_FRAC = 0.15
TEST_FRAC = 0.15


def time_split(items: list, time_key) -> tuple[list, list, list]:
    """Sort `items` by `time_key(item)` and slice into (pool, calib, test) at POOL_FRAC/CALIB_FRAC.

    The only place a split boundary is computed. Import this rather than re-deriving fractions.
    """
    ordered = sorted(items, key=time_key)
    n = len(ordered)
    pool_end = round(n * POOL_FRAC)
    calib_end = pool_end + round(n * CALIB_FRAC)
    return ordered[:pool_end], ordered[pool_end:calib_end], ordered[calib_end:]


# --- brand audit -----------------------------------------------------------
# DECISION: patterns below are the deflection/resolution heuristics from BUILD_SPEC.md §4,
# kept here (not inlined in brand_audit.py) so any other module that needs to know "is this a
# deflection" uses the same definition.
DEFLECTION_PATTERNS = [
    r"\bDMs?\b",
    r"\bsend us a\b",
    r"\bmessage us\b",
    r"twitter\.com/messages",
    r"\bfollow and DM\b",
    r"\bPM us\b",
    # DECISION: added after auditing the real corpus — AmazonHelp's dominant redirect is a
    # link-gated handoff ("please contact us here: <url> so we can assist you accordingly"),
    # functionally identical to "DM us" but not matching the literal DM keyword. Confirmed via
    # sampling that these phrases concentrate in AmazonHelp/Uber_Support and rarely appear in
    # brands that link to genuine public troubleshooting content (docs/DECISION_LOG.md #21).
    r"\bcontact us here\b",
    r"\breach us\b",
    r"\b(provide|fill in|drop in|give us) your details\b",
    r"\bassist you accordingly\b",
    r"\bwe'll get in touch with you\b",
]

RESOLUTION_PATTERNS = [
    r"\bthanks\b",
    r"\bthank you\b",
    r"\bsorted\b",
    r"\bworks now\b",
    r"\bfixed\b",
    r"\U0001F44D",  # 👍
]

MIN_THREADS_FOR_BRAND = 50  # ingest drops brands with fewer reconstructed threads than this
TOP_N_BRANDS_FOR_AUDIT = 15
MIN_THREADS_FOR_BRAND_PICK = 5000  # BUILD_SPEC.md §4: only pick a brand above this volume
AUDIT_TOPIC_KMEANS_K = 20
AUDIT_TOPIC_SAMPLE_SIZE = 2000  # DECISION: cap per-brand sample for the audit's topic_entropy
# KMeans so 15 brands run in seconds, not minutes. This is a descriptive stat, not part of
# answerability_score, so it doesn't need the full corpus.

# --- chosen brand (Phase 1 output) ---------------------------------------
CHOSEN_BRAND = "hulu_support"  # picked by brand_audit.py; see docs/DECISION_LOG.md #1

# --- embeddings ------------------------------------------------------------
# DECISION: BAAI/bge-small-en-v1.5, fixed project-wide (BUILD_SPEC.md §2). Cited in CITATIONS.md.
BGE_MODEL_NAME = "BAAI/bge-small-en-v1.5"
BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

# --- taxonomy induction (Phase 2) ------------------------------------------
TAXONOMY_SAMPLE_SIZE = 4000
TAXONOMY_KMEANS_K = 30
TAXONOMY_STABILITY_SEEDS = [1, 2]
TAXONOMY_STABILITY_KS = [24, 36]

# --- retrieval index (Phase 3) ----------------------------------------------
RETRIEVAL_TOP_K = 8
RETRIEVAL_MMR_K = 3
RETRIEVAL_MMR_LAMBDA = 0.5
RETRIEVAL_DIVERSITY_SAMPLE_SIZE = 50  # queries sampled for the before/after duplication report

# --- playbooks + voice profile (Phase 3) ------------------------------------
PLAYBOOK_REPLIES_PER_INTENT = 100
VOICE_PROFILE_SAMPLE_SIZE = 300

# --- ablations (Phase 5) ----------------------------------------------------
# DECISION: full grid per BUILD_SPEC.md §9.2 is -retrieval/-playbook/-linter/-self_consistency/
# -conformal. Dropped only -playbook: it and -retrieval are the only two that change the draft
# prompt (fresh Gemini calls); -linter/-self_consistency/-conformal are downstream of generation
# or reuse fewer of the same cached samples, so they cost nothing extra and stay in the grid.
# See docs/DECISION_LOG.md #29 for the call-volume estimate that drove this.
ABLATIONS = ["retrieval", "linter", "self_consistency", "conformal"]

# --- golden set sampling (BUILD_SPEC.md §9.1 / docs/ANNOTATION_GUIDE.md §1) -
GOLDEN_N_NATURAL = 120
GOLDEN_N_RARE_INTENT = 40
GOLDEN_N_HARD = 25
GOLDEN_N_REDTEAM = 15
GOLDEN_N_RARE_INTENTS_TO_USE = 4  # "the 4 lowest-frequency intents"
GOLDEN_N_REFERENCE_REPLY_NATURAL = 40  # docs/ANNOTATION_GUIDE.md §2's 60-item subset
GOLDEN_N_REFERENCE_REPLY_HARD = 20

# --- agent (Phase 4, BUILD_SPEC.md §7) --------------------------------------
DRAFT_TEMPERATURE = 0.7
SELF_CONSISTENCY_SALTS = ["", "sample1", "sample2"]  # distinct cache keys for 3 real samples

# DECISION: risk_score is a real feature vector with a HAND-SET placeholder weighting.
# Phase 6b fits the actual logistic regression on calib-split human labels and replaces this
# (BUILD_SPEC.md §7.4) -- these weights and the decision threshold below are not calibrated to
# anything and must not be quoted as a result. See docs/DECISION_LOG.md.
RISK_PLACEHOLDER_WEIGHTS = {
    "margin_uncertainty": 0.15,
    "retrieval_uncertainty": 0.10,
    "consistency_uncertainty": 0.15,
    "needs_account_access": 0.25,
    "linter_violations": 0.15,
    "unsupported_claims": 0.15,
    "anger_severity": 0.05,
}
RISK_MAX_LINTER_VIOLATIONS_FOR_NORMALIZATION = 3
RISK_DECISION_THRESHOLD_PLACEHOLDER = 0.5

# DECISION: hard override, NOT a placeholder -- unlike RISK_PLACEHOLDER_WEIGHTS above, this
# threshold is never fit by Phase 5's logistic regression. Same asymmetric-cost logic as
# BUILD_SPEC.md §7.4's other hard overrides (self-harm/legal/PII/injection): a near-fully-
# ungrounded draft must never auto-send regardless of what the rest of the risk score says.
# Motivating evidence: a real trace with unsupported_claim_rate=1.00 scored risk=0.23 under the
# placeholder weights and would have auto-sent. See docs/DECISION_LOG.md #41.
UNSUPPORTED_CLAIM_OVERRIDE_THRESHOLD = 0.8

# --- judge (Phase 6a, BUILD_SPEC.md §9.3-9.4) --------------------------------
# DECISION: BUILD_SPEC.md §0's thesis names 4 qualities -- "groundedness + actionability +
# safety + voice" -- for a 5-dimension rubric, without spelling out the 5th or exact field
# names anywhere. Added "clarity" (is the reply well-formed and complete, not cut off or
# confusing) as the 5th: it's the natural complement to the other four, and BUILD_SPEC.md
# §9.4's own trap-set defect list includes "truncated mid-sentence", which isn't a
# groundedness/actionability/safety/voice problem -- it needs a dimension to land on.
# See docs/DECISION_LOG.md.
RUBRIC_DIMENSIONS = ["groundedness", "actionability", "safety", "voice", "clarity"]
RUBRIC_SCALE_MIN = 1
RUBRIC_SCALE_MAX = 5

TRAP_SET_SIZE = 40  # BUILD_SPEC.md §9.4.2's explicit number
BIAS_PROBE_SAMPLE_SIZE = 15  # not specified by spec for position/length/self-preference probes;
# kept small relative to the trap set's 40 since each of the 3 probes needs its own multiple-
# call-per-item pass on local, unlimited but not-instant Ollama inference.

# Which rubric dimension each trap-set defect is expected to depress (docs/DECISION_LOG.md).
DEFECT_TO_DIMENSION = {
    "invented_policy": "groundedness",
    "wrong_intent": "actionability",
    "pii_request": "safety",
    "unbounded_promise": "groundedness",
    "wrong_signoff_voice": "voice",
    "truncated_mid_sentence": "clarity",
    "subtly_wrong_product_name": "groundedness",
}

LENGTH_PROBE_FILLER = (" Thank you so much for your patience and for being a valued member of "
                        "our community -- we really do appreciate you reaching out today.")
