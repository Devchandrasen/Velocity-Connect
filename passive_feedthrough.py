"""Measured passive-feedthrough link-budget helpers.

This module contains no built-in or synthetic measurement rows. It converts
calibrated VNA/OTA records into the exact component terms consumed by the
system-level simulator.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import Iterable, Mapping

from statistical_evidence import ci95_half_width


MEASUREMENT_FIELDS = {
    "sample_id",
    "frequency_hz",
    "feeder_s21_db",
    "feedthrough_s21_db",
    "coupling_loss_db",
    "indoor_path_loss_db",
    "donor_gain_dbi",
    "service_gain_dbi",
}


def _finite(name: str, value: object) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


@dataclass(frozen=True)
class PassiveBudget:
    feeder_loss_db: float
    coupling_loss_db: float
    indoor_path_loss_db: float
    donor_gain_dbi: float
    service_gain_dbi: float

    def validate(self) -> None:
        for name, value in (
            ("feeder_loss_db", self.feeder_loss_db),
            ("coupling_loss_db", self.coupling_loss_db),
            ("indoor_path_loss_db", self.indoor_path_loss_db),
            ("donor_gain_dbi", self.donor_gain_dbi),
            ("service_gain_dbi", self.service_gain_dbi),
        ):
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and non-negative")
        if self.equivalent_loss_db < 0:
            raise ValueError(
                "component budget produces net gain; the current system-level "
                "abstraction requires non-negative equivalent loss"
            )

    @property
    def network_loss_db(self) -> float:
        return self.feeder_loss_db + self.coupling_loss_db

    @property
    def aperture_gain_db(self) -> float:
        return self.donor_gain_dbi + self.service_gain_dbi

    @property
    def equivalent_loss_db(self) -> float:
        return (
            self.network_loss_db
            + self.indoor_path_loss_db
            - self.aperture_gain_db
        )


def budget_from_measurement(row: Mapping[str, object]) -> tuple[str, float, PassiveBudget]:
    missing = MEASUREMENT_FIELDS.difference(row)
    if missing:
        raise ValueError(f"measurement row is missing fields: {sorted(missing)}")

    sample_id = str(row["sample_id"]).strip()
    if not sample_id:
        raise ValueError("sample_id cannot be empty")
    frequency_hz = _finite("frequency_hz", row["frequency_hz"])
    if frequency_hz <= 0:
        raise ValueError("frequency_hz must be positive")

    feeder_s21_db = _finite("feeder_s21_db", row["feeder_s21_db"])
    feedthrough_s21_db = _finite("feedthrough_s21_db", row["feedthrough_s21_db"])
    if feeder_s21_db > 0 or feedthrough_s21_db > 0:
        raise ValueError("passive S21 values must be zero or negative dB")

    coupling_loss_db = _finite("coupling_loss_db", row["coupling_loss_db"])
    budget = PassiveBudget(
        feeder_loss_db=-feeder_s21_db,
        coupling_loss_db=-feedthrough_s21_db + coupling_loss_db,
        indoor_path_loss_db=_finite(
            "indoor_path_loss_db", row["indoor_path_loss_db"]
        ),
        donor_gain_dbi=_finite("donor_gain_dbi", row["donor_gain_dbi"]),
        service_gain_dbi=_finite("service_gain_dbi", row["service_gain_dbi"]),
    )
    budget.validate()
    return sample_id, frequency_hz, budget


def summarize_budgets(budgets: Iterable[PassiveBudget]) -> dict[str, float | int]:
    values = [budget.equivalent_loss_db for budget in budgets]
    if not values:
        raise ValueError("at least one measured budget is required")
    mean = statistics.fmean(values)
    std = statistics.stdev(values) if len(values) > 1 else 0.0
    ci95 = ci95_half_width(values)
    return {
        "n_samples": len(values),
        "equivalent_loss_db_mean": mean,
        "equivalent_loss_db_std": std,
        "equivalent_loss_db_ci95": ci95,
        "equivalent_loss_db_min": min(values),
        "equivalent_loss_db_max": max(values),
    }
