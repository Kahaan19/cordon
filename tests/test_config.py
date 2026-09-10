"""Test 3 from BUILD_SPEC.md §13."""
from __future__ import annotations

import random

from config import time_split


def test_time_split_has_no_id_overlap_and_is_strictly_ordered():
    items = [{"id": i, "t": i} for i in range(100)]
    shuffled = items[:]
    random.Random(0).shuffle(shuffled)

    pool, calib, test = time_split(shuffled, time_key=lambda x: x["t"])

    all_ids = [x["id"] for x in pool] + [x["id"] for x in calib] + [x["id"] for x in test]
    assert len(all_ids) == 100
    assert len(set(all_ids)) == 100

    assert [x["t"] for x in pool] == sorted(x["t"] for x in pool)
    assert [x["t"] for x in calib] == sorted(x["t"] for x in calib)
    assert [x["t"] for x in test] == sorted(x["t"] for x in test)
    assert max(x["t"] for x in pool) <= min(x["t"] for x in calib)
    assert max(x["t"] for x in calib) <= min(x["t"] for x in test)
