"""Passivity-constrained RF-to-system feasibility helpers.

The functions in this module describe a simulated passive feedthrough. They do
not convert antenna-to-antenna isolation (for example, donor-array S12) into an
end-to-end feedthrough transmission coefficient, and they do not represent
hardware measurements.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class PassiveCorner:
    """One declared uncertainty corner of the passive feedthrough abstraction."""

    name: str
    feeder_loss_db: float
    coupling_loss_db: float
    indoor_path_loss_db: float
    donor_gain_dbi: float
    service_gain_dbi: float

    def validate(self) -> None:
        if not self.name.strip():
            raise ValueError("corner name cannot be empty")
        for field, value in (
            ("feeder_loss_db", self.feeder_loss_db),
            ("coupling_loss_db", self.coupling_loss_db),
            ("indoor_path_loss_db", self.indoor_path_loss_db),
            ("donor_gain_dbi", self.donor_gain_dbi),
            ("service_gain_dbi", self.service_gain_dbi),
        ):
            if not math.isfinite(value) or value < 0.0:
                raise ValueError(f"{field} must be finite and non-negative")
        if self.equivalent_loss_db < 0.0:
            raise ValueError(
                "the scalar system abstraction does not support net passive gain"
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

    def break_even_network_loss_db(self, direct_penetration_loss_db: float) -> float:
        """Maximum passive-network loss that still beats direct penetration."""

        if (
            not math.isfinite(direct_penetration_loss_db)
            or direct_penetration_loss_db < 0.0
        ):
            raise ValueError(
                "direct_penetration_loss_db must be finite and non-negative"
            )
        return (
            direct_penetration_loss_db
            + self.aperture_gain_db
            - self.indoor_path_loss_db
        )


def reciprocal_two_port(
    *,
    return_loss_db: float,
    insertion_loss_db: float,
) -> np.ndarray:
    """Construct a reciprocal illustrative two-port with an orthogonal phase.

    The opposite sign on S22 makes the reflected and transmitted columns
    orthogonal. The network is passive exactly when ``|r|^2 + |t|^2 <= 1``.
    This matrix is an analytical passivity check for a declared insertion-loss
    corner, not an HFSS export of the complete donor-feedline-service assembly.
    """

    for name, value in (
        ("return_loss_db", return_loss_db),
        ("insertion_loss_db", insertion_loss_db),
    ):
        if not math.isfinite(value) or value < 0.0:
            raise ValueError(f"{name} must be finite and non-negative")
    reflection = 10.0 ** (-return_loss_db / 20.0)
    transmission = 10.0 ** (-insertion_loss_db / 20.0)
    return np.asarray(
        [
            [reflection, transmission],
            [transmission, -reflection],
        ],
        dtype=complex,
    )


def maximum_singular_value(s_matrix: np.ndarray) -> float:
    """Return the largest singular value of a square power-wave S matrix."""

    matrix = np.asarray(s_matrix, dtype=complex)
    if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1]:
        raise ValueError("s_matrix must be square")
    if matrix.size == 0 or not np.isfinite(matrix).all():
        raise ValueError("s_matrix must be non-empty and finite")
    return float(np.linalg.svd(matrix, compute_uv=False)[0])


def is_passive(s_matrix: np.ndarray, tolerance: float = 1e-9) -> bool:
    """Check the power-wave singular-value passivity condition."""

    if not math.isfinite(tolerance) or tolerance < 0.0:
        raise ValueError("tolerance must be finite and non-negative")
    return maximum_singular_value(s_matrix) <= 1.0 + tolerance


PUBLICATION_CORNERS = (
    PassiveCorner(
        name="optimistic",
        feeder_loss_db=1.5,
        coupling_loss_db=5.0,
        indoor_path_loss_db=3.0,
        donor_gain_dbi=5.545,
        service_gain_dbi=2.5,
    ),
    PassiveCorner(
        name="nominal",
        feeder_loss_db=2.0,
        coupling_loss_db=7.0,
        indoor_path_loss_db=5.0,
        donor_gain_dbi=5.545,
        service_gain_dbi=2.0,
    ),
    PassiveCorner(
        name="conservative",
        feeder_loss_db=3.0,
        coupling_loss_db=12.0,
        indoor_path_loss_db=8.0,
        donor_gain_dbi=0.453,
        service_gain_dbi=0.0,
    ),
)
