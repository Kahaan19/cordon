"""Test 14 from BUILD_SPEC.md §13 (golden-set half): all strata present, no test/pool leakage.
The labelled-golden-set half (no missing labels) is skipped until data/golden/golden_v1.jsonl
exists -- that file is produced by a human labelling session, not by any automated step.
"""
from __future__ import annotations

import json

import pytest

from config import CHOSEN_BRAND, GOLDEN_DIR, INTERIM_DIR, time_split
from cordon.schemas import Thread

SAMPLED_PATH = GOLDEN_DIR / "sampled_items.jsonl"
GOLDEN_PATH = GOLDEN_DIR / "golden_v1.jsonl"

REQUIRED_LABEL_FIELDS = {
    "intent", "secondary_intent", "needs_account_access", "severity", "anger",
    "contains_pii", "multi_intent", "should_escalate", "escalate_reason", "stratum",
}


def _load_jsonl(path):
    with open(path) as f:
        return [json.loads(line) for line in f]


@pytest.mark.skipif(not SAMPLED_PATH.exists(), reason="run `make sample` first")
def test_sampled_items_have_all_strata_and_no_pool_leakage():
    items = _load_jsonl(SAMPLED_PATH)
    assert {i["stratum"] for i in items} == {"natural", "rare_intent", "hard", "redteam"}

    threads = [Thread.model_validate_json(line)
               for line in open(INTERIM_DIR / f"threads_{CHOSEN_BRAND}.jsonl")]
    pool, _, test = time_split(threads, time_key=lambda t: t.created_at_root)
    pool_ids = {t.thread_id for t in pool}
    test_ids = {t.thread_id for t in test}

    real_thread_ids = {i["thread_id"] for i in items if not i["synthetic"]}
    assert real_thread_ids.isdisjoint(pool_ids)
    assert real_thread_ids <= test_ids


@pytest.mark.skipif(not GOLDEN_PATH.exists(), reason="golden_v1.jsonl not labelled yet")
def test_golden_set_has_no_missing_labels():
    items = _load_jsonl(GOLDEN_PATH)
    assert {i["stratum"] for i in items} == {"natural", "rare_intent", "hard", "redteam"}
    for item in items:
        assert REQUIRED_LABEL_FIELDS <= set(item.keys())
        assert item["intent"] is not None
        if item["should_escalate"]:
            assert item["escalate_reason"]
        if item["multi_intent"]:
            assert item["secondary_intent"] is not None
