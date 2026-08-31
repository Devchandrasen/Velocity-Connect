import math

import pytest

from statistical_evidence import bootstrap_mean_ci95


def test_bootstrap_mean_interval_is_deterministic_and_contains_mean():
    values = [0.81, 0.86, 0.91, 0.96, 0.99]
    first = bootstrap_mean_ci95(values, seed=20260825)
    second = bootstrap_mean_ci95(values, seed=20260825)
    assert first == second
    assert first[0] < sum(values) / len(values) < first[1]


def test_bootstrap_mean_interval_handles_singleton_and_empty_samples():
    assert bootstrap_mean_ci95([3.5], seed=7) == (3.5, 3.5)
    lower, upper = bootstrap_mean_ci95([], seed=7)
    assert math.isnan(lower) and math.isnan(upper)


def test_bootstrap_rejects_nonfinite_values_and_too_few_resamples():
    with pytest.raises(ValueError, match="finite"):
        bootstrap_mean_ci95([1.0, math.nan], seed=7)
    with pytest.raises(ValueError, match="at least 1000"):
        bootstrap_mean_ci95([1.0, 2.0], seed=7, resamples=999)
