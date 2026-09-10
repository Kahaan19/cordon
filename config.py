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
# DECISION: gemini-flash-latest is the current free-tier Flash alias per
# aistudio.google.com/apikey as of the last time this was checked. Re-verify before a long run —
# free-tier model IDs and limits move.
GEN_MODEL = "gemini-flash-latest"
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
