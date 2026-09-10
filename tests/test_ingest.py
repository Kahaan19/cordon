"""Tests 1-2 from BUILD_SPEC.md §13."""
from __future__ import annotations

import pandas as pd

from cordon.ingest import clean_text, reconstruct_threads


def test_clean_text_strips_handle_keeps_emoji_masks_url():
    text = "@AmazonHelp my package is late \U0001F621 check http://t.co/xyz123 cc @otherUser"
    cleaned, flags = clean_text(text)

    assert not cleaned.startswith("@AmazonHelp")
    assert "\U0001F621" in cleaned
    assert "<url>" in cleaned and "http://t.co" not in cleaned
    assert "@user" in cleaned
    assert flags["had_url"] is True


def test_thread_reconstruction_follows_earliest_child_on_branch():
    t0, t1, t2, t3, t4 = (
        pd.Timestamp("2017-10-31T22:00:00Z"), pd.Timestamp("2017-10-31T22:05:00Z"),
        pd.Timestamp("2017-10-31T22:10:00Z"), pd.Timestamp("2017-10-31T22:15:00Z"),
        pd.Timestamp("2017-10-31T22:20:00Z"),
    )
    rows = {
        "t1": ("cust1", True, t0, "@BrandX help me", ["t2", "t3"], None),
        "t2": ("BrandX", False, t1, "we are on it", ["t4"], "t1"),
        "t3": ("BrandX", False, t2, "a slower duplicate branch reply", [], "t1"),
        "t4": ("cust1", True, t3, "thanks, still broken", ["t5"], "t2"),
        "t5": ("BrandX", False, t4, "try this fix", [], "t4"),
    }

    threads, dropped_stats = reconstruct_threads(rows)

    assert len(threads) == 1
    thread = threads[0]
    assert thread.thread_id == "t1"
    assert thread.brand == "BrandX"
    assert thread.n_turns == 4
    assert thread.n_branches == 1
    assert [t.tweet_id for t in thread.turns] == ["t1", "t2", "t4", "t5"]
    assert thread.first_customer_msg == "help me"
    assert dropped_stats == {}


def test_thread_with_no_agent_turn_is_dropped():
    t0 = pd.Timestamp("2017-10-31T22:00:00Z")
    rows = {"t1": ("cust1", True, t0, "hello anyone home", [], None)}

    threads, dropped_stats = reconstruct_threads(rows)

    assert threads == []
    assert dropped_stats == {"no_agent_turn": 1}
