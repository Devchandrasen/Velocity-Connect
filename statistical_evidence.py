"""Small-sample confidence-interval helpers for experiment evidence."""

from __future__ import annotations

import math
import statistics
from collections.abc import Sequence

import numpy as np


# Two-sided 95% Student-t critical values, indexed by degrees of freedom.
_T_975 = (
    math.nan,
    12.706,
    4.303,
    3.182,
    2.776,
    2.571,
    2.447,
    2.365,
    2.306,
    2.262,
    2.228,
    2.201,
    2.179,
    2.160,
    2.145,
    2.131,
    2.120,
    2.110,
    2.101,
    2.093,
    2.086,
    2.080,
    2.074,
    2.069,
    2.064,
    2.060,
    2.056,
    2.052,
    2.048,
    2.045,
    2.042,
)


def t_critical_95(degrees_of_freedom: int) -> float:
    """Return the two-sided 95% Student-t critical value."""

    if degrees_of_freedom < 1:
        raise ValueError("degrees_of_freedom must be at least 1")
    if degrees_of_freedom < len(_T_975):
        return _T_975[degrees_of_freedom]

    # Cornish-Fisher expansion around z=1.959963984540054. For df > 30
    # this is more accurate than silently using 1.96.
    z = 1.959963984540054
    df = float(degrees_of_freedom)
    return (
        z
        + (z**3 + z) / (4.0 * df)
        + (5.0 * z**5 + 16.0 * z**3 + 3.0 * z) / (96.0 * df**2)
        + (3.0 * z**7 + 19.0 * z**5 + 17.0 * z**3 - 15.0 * z)
        / (384.0 * df**3)
    )


def ci95_half_width(values: Sequence[float]) -> float:
    """Return a two-sided 95% mean-CI half width using sample SD."""

    if len(values) < 2:
        return 0.0
    std = statistics.stdev(values)
    return t_critical_95(len(values) - 1) * std / math.sqrt(len(values))


def bootstrap_mean_ci95(
    values: Sequence[float],
    *,
    seed: int,
    resamples: int = 20_000,
) -> tuple[float, float]:
    """Return a deterministic percentile-bootstrap interval for a run mean."""

    array = np.asarray(values, dtype=float)
    if array.size == 0:
        return math.nan, math.nan
    if not np.isfinite(array).all():
        raise ValueError("bootstrap values must be finite")
    if array.size == 1:
        value = float(array[0])
        return value, value
    if resamples < 1_000:
        raise ValueError("resamples must be at least 1000")
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, array.size, size=(resamples, array.size))
    means = array[indices].mean(axis=1)
    lower, upper = np.quantile(means, [0.025, 0.975], method="linear")
    return float(lower), float(upper)
