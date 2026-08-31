"""Passivity-safe models for a polarization-twisted passive feedthrough.

The proposed PTF-MIMO assembly uses two reciprocal shielded RF channels.  A
straight control maps donor mode 1 to service mode 1 and donor mode 2 to
service mode 2.  The proposed topology swaps the service modes, so donor mode
1 is reradiated by service mode 2 and vice versa.  This module contains only
analytical and simulation-facing helpers; it does not represent a measured
four-port product.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable, Sequence

import numpy as np


def _finite_nonnegative(name: str, value: float) -> float:
    result = float(value)
    if not math.isfinite(result) or result < 0.0:
        raise ValueError(f"{name} must be finite and non-negative")
    return result


def db_to_voltage(loss_db: float) -> float:
    """Convert a non-negative voltage-wave loss in dB to linear magnitude."""

    return 10.0 ** (-_finite_nonnegative("loss_db", loss_db) / 20.0)


def maximum_singular_value(matrix: np.ndarray) -> float:
    values = np.asarray(matrix, dtype=complex)
    if values.ndim != 2 or values.shape[0] != values.shape[1] or values.size == 0:
        raise ValueError("matrix must be non-empty and square")
    if not np.isfinite(values).all():
        raise ValueError("matrix must be finite")
    return float(np.linalg.svd(values, compute_uv=False)[0])


def minimum_singular_value(matrix: np.ndarray) -> float:
    values = np.asarray(matrix, dtype=complex)
    if values.ndim != 2 or values.size == 0:
        raise ValueError("matrix must be a non-empty two-dimensional array")
    if not np.isfinite(values).all():
        raise ValueError("matrix must be finite")
    return float(np.linalg.svd(values, compute_uv=False)[-1])


def four_port_feedthrough(
    frequencies_hz: Sequence[float],
    *,
    insertion_loss_db: float,
    return_loss_db: float,
    differential_delay_s: float = 0.0,
    topology: str = "cross",
) -> np.ndarray:
    """Create a reciprocal, contractive four-port feedthrough model.

    Port order is ``D1, D2, S1, S2``.  In the straight control, intended
    transfers are D1-S1 and D2-S2.  In the cross topology, intended transfers
    are D1-S2 and D2-S1.  The second channel has the requested differential
    delay.  Reflections have opposite signs at opposite ends of a channel,
    which keeps the two-port columns orthogonal.  Every frequency slice has
    spectral norm ``sqrt(|r|^2 + |t|^2)`` and is rejected if that exceeds one.
    """

    frequencies = np.asarray(frequencies_hz, dtype=float)
    if frequencies.ndim != 1 or frequencies.size == 0:
        raise ValueError("frequencies_hz must be a non-empty one-dimensional array")
    if not np.isfinite(frequencies).all() or np.any(frequencies <= 0.0):
        raise ValueError("frequencies_hz must be finite and positive")
    if topology not in {"straight", "cross"}:
        raise ValueError("topology must be 'straight' or 'cross'")
    delay = float(differential_delay_s)
    if not math.isfinite(delay):
        raise ValueError("differential_delay_s must be finite")

    reflection = db_to_voltage(return_loss_db)
    transmission = db_to_voltage(insertion_loss_db)
    contraction = math.hypot(reflection, transmission)
    if contraction > 1.0 + 1e-12:
        raise ValueError(
            "return and insertion losses violate passive power-wave contraction"
        )

    pairs = ((0, 2), (1, 3)) if topology == "straight" else ((0, 3), (1, 2))
    matrices = np.zeros((frequencies.size, 4, 4), dtype=complex)
    for frequency_index, frequency_hz in enumerate(frequencies):
        phases = (0.0, -2.0 * math.pi * float(frequency_hz) * delay)
        for channel_index, (donor_port, service_port) in enumerate(pairs):
            transfer = transmission * np.exp(1j * phases[channel_index])
            matrices[frequency_index, donor_port, donor_port] = reflection
            matrices[frequency_index, service_port, service_port] = -reflection
            matrices[frequency_index, donor_port, service_port] = transfer
            matrices[frequency_index, service_port, donor_port] = transfer
        if maximum_singular_value(matrices[frequency_index]) > 1.0 + 1e-9:
            raise RuntimeError("constructed feedthrough is not passive")
    return matrices


def relay_mode_matrix(
    frequency_hz: float,
    *,
    insertion_loss_db: float,
    differential_delay_s: float,
    topology: str,
) -> np.ndarray:
    """Return the donor-to-service 2x2 transfer block used by co-design."""

    frequency = float(frequency_hz)
    if not math.isfinite(frequency) or frequency <= 0.0:
        raise ValueError("frequency_hz must be finite and positive")
    if topology not in {"straight", "cross"}:
        raise ValueError("topology must be 'straight' or 'cross'")
    magnitude = db_to_voltage(insertion_loss_db)
    phase = np.exp(-2j * math.pi * frequency * float(differential_delay_s))
    straight = magnitude * np.diag([1.0 + 0.0j, phase])
    if topology == "straight":
        return straight
    swap = np.asarray([[0.0, 1.0], [1.0, 0.0]], dtype=complex)
    return swap @ straight


def donor_to_service_block(four_port_matrices: np.ndarray) -> np.ndarray:
    """Extract the service-output versus donor-input block from a four-port.

    The required port order is ``D1, D2, S1, S2``.  For an S-matrix using
    the conventional ``S[output, input]`` indexing, the returned 2x2 block is
    ``[[S31, S32], [S41, S42]]`` at every frequency.
    """

    matrices = np.asarray(four_port_matrices, dtype=complex)
    if matrices.ndim == 2:
        matrices = matrices[np.newaxis, ...]
    if matrices.ndim != 3 or matrices.shape[1:] != (4, 4):
        raise ValueError("four_port_matrices must have shape (frequency, 4, 4)")
    if not np.isfinite(matrices).all():
        raise ValueError("four_port_matrices must be finite")
    return matrices[:, 2:4, 0:2].copy()


def straight_control_from_cross_blocks(cross_blocks: np.ndarray) -> np.ndarray:
    """Create the co-polar straight control by undoing the service-row swap."""

    blocks = np.asarray(cross_blocks, dtype=complex)
    if blocks.ndim == 2:
        blocks = blocks[np.newaxis, ...]
    if blocks.ndim != 3 or blocks.shape[1:] != (2, 2):
        raise ValueError("cross_blocks must have shape (frequency, 2, 2)")
    if not np.isfinite(blocks).all():
        raise ValueError("cross_blocks must be finite")
    swap = np.asarray([[0.0, 1.0], [1.0, 0.0]], dtype=complex)
    return np.einsum("ij,fjk->fik", swap, blocks)


def apply_differential_delay(
    frequencies_hz: Sequence[float],
    feedthrough_blocks: np.ndarray,
    differential_delay_s: float,
) -> np.ndarray:
    """Apply a realizable extra delay to donor mode 2 of an EM feedthrough."""

    frequencies = np.asarray(frequencies_hz, dtype=float)
    blocks = np.asarray(feedthrough_blocks, dtype=complex)
    if frequencies.ndim != 1 or frequencies.size == 0:
        raise ValueError("frequencies_hz must be non-empty and one-dimensional")
    if not np.isfinite(frequencies).all() or np.any(frequencies <= 0.0):
        raise ValueError("frequencies_hz must be finite and positive")
    if blocks.shape != (frequencies.size, 2, 2):
        raise ValueError(
            "feedthrough_blocks must have shape (len(frequencies_hz), 2, 2)"
        )
    if not np.isfinite(blocks).all():
        raise ValueError("feedthrough_blocks must be finite")
    delay = float(differential_delay_s)
    if not math.isfinite(delay):
        raise ValueError("differential_delay_s must be finite")

    delayed = blocks.copy()
    delayed[:, :, 1] *= np.exp(-2j * math.pi * frequencies * delay)[:, None]
    return delayed


@dataclass(frozen=True)
class ChannelScenario:
    """One frequency-aligned 2x2 direct-plus-relay channel scenario."""

    name: str
    direct: np.ndarray
    donor_capture: np.ndarray
    service_radiation: np.ndarray

    def validate(self, frequency_count: int) -> None:
        if not self.name.strip():
            raise ValueError("scenario name cannot be empty")
        for field_name, value in (
            ("direct", self.direct),
            ("donor_capture", self.donor_capture),
            ("service_radiation", self.service_radiation),
        ):
            matrix = np.asarray(value, dtype=complex)
            if matrix.shape != (frequency_count, 2, 2):
                raise ValueError(
                    f"{field_name} must have shape ({frequency_count}, 2, 2)"
                )
            if not np.isfinite(matrix).all():
                raise ValueError(f"{field_name} must be finite")


def evaluate_delay_candidate(
    frequencies_hz: Sequence[float],
    scenarios: Iterable[ChannelScenario],
    *,
    insertion_loss_db: float,
    differential_delay_s: float,
    topology: str,
) -> dict[str, object]:
    """Evaluate the exact robust objective used by the minimax selector."""

    frequencies = np.asarray(frequencies_hz, dtype=float)
    if frequencies.ndim != 1 or frequencies.size == 0:
        raise ValueError("frequencies_hz must be non-empty and one-dimensional")
    scenario_list = list(scenarios)
    if not scenario_list:
        raise ValueError("at least one channel scenario is required")
    for scenario in scenario_list:
        scenario.validate(frequencies.size)

    samples: list[dict[str, object]] = []
    worst_value = math.inf
    worst_descriptor: dict[str, object] | None = None
    for scenario in scenario_list:
        direct = np.asarray(scenario.direct, dtype=complex)
        donor = np.asarray(scenario.donor_capture, dtype=complex)
        service = np.asarray(scenario.service_radiation, dtype=complex)
        for frequency_index, frequency_hz in enumerate(frequencies):
            feed = relay_mode_matrix(
                float(frequency_hz),
                insertion_loss_db=insertion_loss_db,
                differential_delay_s=differential_delay_s,
                topology=topology,
            )
            composite = (
                direct[frequency_index]
                + service[frequency_index] @ feed @ donor[frequency_index]
            )
            sigma_min = minimum_singular_value(composite)
            descriptor = {
                "scenario": scenario.name,
                "frequency_hz": float(frequency_hz),
                "sigma_min": sigma_min,
            }
            samples.append(descriptor)
            if sigma_min < worst_value:
                worst_value = sigma_min
                worst_descriptor = descriptor
    return {
        "topology": topology,
        "differential_delay_s": float(differential_delay_s),
        "robust_objective_min_sigma": float(worst_value),
        "worst_sample": worst_descriptor,
        "sample_count": len(samples),
        "samples": samples,
    }


def select_minimax_delay(
    frequencies_hz: Sequence[float],
    scenarios: Iterable[ChannelScenario],
    candidate_delays_s: Sequence[float],
    *,
    insertion_loss_db: float,
    topology: str,
) -> dict[str, object]:
    """Maximize the minimum composite-channel singular value.

    This is deliberately a finite, auditable candidate search.  It implements
    ``arg max_delay min_(scenario, frequency) sigma_min(H_total)`` exactly;
    no surrogate score or post-hoc weighted objective is used.
    """

    delays = [float(value) for value in candidate_delays_s]
    if not delays or not all(math.isfinite(value) for value in delays):
        raise ValueError("candidate_delays_s must contain finite values")
    scenario_list = list(scenarios)
    evaluations = [
        evaluate_delay_candidate(
            frequencies_hz,
            scenario_list,
            insertion_loss_db=insertion_loss_db,
            differential_delay_s=delay,
            topology=topology,
        )
        for delay in delays
    ]
    selected = max(
        evaluations,
        key=lambda row: (
            float(row["robust_objective_min_sigma"]),
            -abs(float(row["differential_delay_s"])),
        ),
    )
    return {
        "objective": (
            "argmax_delay min_scenario,frequency "
            "sigma_min(H_direct + H_service F_delay H_donor)"
        ),
        "topology": topology,
        "selected_delay_s": selected["differential_delay_s"],
        "selected_objective_min_sigma": selected["robust_objective_min_sigma"],
        "selected_worst_sample": selected["worst_sample"],
        "evaluations": evaluations,
    }


def evaluate_em_feedthrough_candidate(
    frequencies_hz: Sequence[float],
    scenarios: Iterable[ChannelScenario],
    feedthrough_blocks: np.ndarray,
    *,
    differential_delay_s: float,
    topology: str,
) -> dict[str, object]:
    """Evaluate one delay using a frequency-dependent EM four-port block."""

    frequencies = np.asarray(frequencies_hz, dtype=float)
    scenario_list = list(scenarios)
    if not scenario_list:
        raise ValueError("at least one channel scenario is required")
    for scenario in scenario_list:
        scenario.validate(frequencies.size)
    delayed_blocks = apply_differential_delay(
        frequencies,
        feedthrough_blocks,
        differential_delay_s,
    )

    samples: list[dict[str, object]] = []
    worst_value = math.inf
    worst_descriptor: dict[str, object] | None = None
    for scenario in scenario_list:
        direct = np.asarray(scenario.direct, dtype=complex)
        donor = np.asarray(scenario.donor_capture, dtype=complex)
        service = np.asarray(scenario.service_radiation, dtype=complex)
        for frequency_index, frequency_hz in enumerate(frequencies):
            composite = (
                direct[frequency_index]
                + service[frequency_index]
                @ delayed_blocks[frequency_index]
                @ donor[frequency_index]
            )
            sigma_min = minimum_singular_value(composite)
            descriptor = {
                "scenario": scenario.name,
                "frequency_hz": float(frequency_hz),
                "sigma_min": sigma_min,
            }
            samples.append(descriptor)
            if sigma_min < worst_value:
                worst_value = sigma_min
                worst_descriptor = descriptor
    return {
        "topology": topology,
        "differential_delay_s": float(differential_delay_s),
        "robust_objective_min_sigma": float(worst_value),
        "worst_sample": worst_descriptor,
        "sample_count": len(samples),
        "samples": samples,
    }


def select_em_minimax_delay(
    frequencies_hz: Sequence[float],
    scenarios: Iterable[ChannelScenario],
    feedthrough_blocks: np.ndarray,
    candidate_delays_s: Sequence[float],
    *,
    topology: str,
) -> dict[str, object]:
    """Run the finite minimax selector with the exported HFSS transfer block."""

    delays = [float(value) for value in candidate_delays_s]
    if not delays or not all(math.isfinite(value) for value in delays):
        raise ValueError("candidate_delays_s must contain finite values")
    scenario_list = list(scenarios)
    evaluations = [
        evaluate_em_feedthrough_candidate(
            frequencies_hz,
            scenario_list,
            feedthrough_blocks,
            differential_delay_s=delay,
            topology=topology,
        )
        for delay in delays
    ]
    selected = max(
        evaluations,
        key=lambda row: (
            float(row["robust_objective_min_sigma"]),
            -abs(float(row["differential_delay_s"])),
        ),
    )
    return {
        "objective": (
            "argmax_delay min_scenario,frequency "
            "sigma_min(H_direct + H_service F_HFSS,delay H_donor)"
        ),
        "topology": topology,
        "selected_delay_s": selected["differential_delay_s"],
        "selected_objective_min_sigma": selected[
            "robust_objective_min_sigma"
        ],
        "selected_worst_sample": selected["worst_sample"],
        "evaluations": evaluations,
    }
