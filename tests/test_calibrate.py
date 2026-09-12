"""Tests 10-11 from BUILD_SPEC.md §13: Clopper-Pearson bound sanity, choose_threshold's
n < 20 refusal."""
from __future__ import annotations

import numpy as np

from cordon.calibrate import choose_threshold, clopper_pearson_upper, split_golden_for_calibration


def test_clopper_pearson_upper_sane_bounds():
    assert clopper_pearson_upper(0, 100) < 0.05
    bounded = clopper_pearson_upper(5, 100)
    assert 0.0 < bounded < 1.0
    assert clopper_pearson_upper(5, 100) < clopper_pearson_upper(10, 100)  # monotone in k
    assert clopper_pearson_upper(100, 100) == 1.0


def test_choose_threshold_never_certifies_below_min_n():
    rng = np.random.RandomState(0)
    scores = rng.uniform(0, 1, size=15)  # fewer than CLOPPER_PEARSON_MIN_N=20 items total
    is_bad = np.zeros(15, dtype=bool)  # even a perfect record can't certify on this little data
    tau, coverage = choose_threshold(scores, is_bad, alpha=0.05)
    assert coverage == 0.0


def test_choose_threshold_certifies_once_enough_clean_evidence_exists():
    rng = np.random.RandomState(0)
    scores = rng.uniform(0, 1, size=100)
    is_bad = np.zeros(100, dtype=bool)  # zero failures anywhere
    tau, coverage = choose_threshold(scores, is_bad, alpha=0.05)
    assert coverage > 0.0  # 100 clean items is enough evidence to certify some coverage


def test_split_golden_for_calibration_is_stratified_and_covers_every_item():
    items = ([{"item_id": f"n{i}", "stratum": "natural"} for i in range(20)]
             + [{"item_id": f"h{i}", "stratum": "hard"} for i in range(10)])
    fit_items, holdout_items = split_golden_for_calibration(items, seed=0, fit_fraction=0.5)

    fit_ids = {i["item_id"] for i in fit_items}
    holdout_ids = {i["item_id"] for i in holdout_items}
    assert fit_ids.isdisjoint(holdout_ids)
    assert fit_ids | holdout_ids == {i["item_id"] for i in items}

    fit_strata = {i["stratum"] for i in fit_items}
    assert fit_strata == {"natural", "hard"}  # both strata represented in the fitting role too
