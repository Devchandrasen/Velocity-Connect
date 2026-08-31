"""Synthesize and tolerance-check a broadband n78 matching network."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
from scipy.optimize import differential_evolution

from ansys.aedt.core import Hfss

from build_n78_donor import AEDT_VERSION, DESIGN_NAME, PROJECT_NAME, SETUP_NAME, SWEEP_NAME


TERMINAL = "port_VC_Donor_Blade_1_T1"
CAPACITOR_Q = 100.0
INDUCTOR_Q = 30.0
TOLERANCE = 0.05
MONTE_CARLO_SAMPLES = 5000


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Use solved HFSS impedance to design a broadband low-pass pi match."
    )
    parser.add_argument(
        "--project",
        type=Path,
        default=Path(__file__).resolve().parent / PROJECT_NAME,
    )
    parser.add_argument("--aedt-process-id", type=int, default=None)
    return parser.parse_args()


def _reflection_db(impedance: np.ndarray) -> np.ndarray:
    gamma = (impedance - 50.0) / (impedance + 50.0)
    return 20.0 * np.log10(np.maximum(np.abs(gamma), 1e-15))


def _capacitor_admittance(
    omega: np.ndarray,
    capacitance_pf: float | np.ndarray,
    quality_factor: float | None = None,
) -> np.ndarray:
    capacitance = np.asarray(capacitance_pf) * 1e-12
    if quality_factor is None:
        return 1j * omega * capacitance
    esr = 1.0 / (omega * capacitance * quality_factor)
    return 1.0 / (esr + 1.0 / (1j * omega * capacitance))


def _inductor_impedance(
    omega: np.ndarray,
    inductance_nh: float | np.ndarray,
    quality_factor: float | None = None,
) -> np.ndarray:
    inductance = np.asarray(inductance_nh) * 1e-9
    resistance = 0.0 if quality_factor is None else omega * inductance / quality_factor
    return resistance + 1j * omega * inductance


def _pi_input_impedance(
    load: np.ndarray,
    omega: np.ndarray,
    load_shunt_cap_pf: float | np.ndarray,
    series_inductor_nh: float | np.ndarray,
    input_shunt_cap_pf: float | np.ndarray,
    lossy: bool,
) -> np.ndarray:
    capacitor_q = CAPACITOR_Q if lossy else None
    inductor_q = INDUCTOR_Q if lossy else None
    after_load_shunt = 1.0 / (
        1.0 / load
        + _capacitor_admittance(
            omega,
            load_shunt_cap_pf,
            capacitor_q,
        )
    )
    after_series = after_load_shunt + _inductor_impedance(
        omega,
        series_inductor_nh,
        inductor_q,
    )
    return 1.0 / (
        1.0 / after_series
        + _capacitor_admittance(
            omega,
            input_shunt_cap_pf,
            capacitor_q,
        )
    )


def _pi_power_metrics(
    load: np.ndarray,
    omega: np.ndarray,
    load_shunt_cap_pf: float,
    series_inductor_nh: float,
    input_shunt_cap_pf: float,
) -> dict[str, np.ndarray]:
    """Return accepted and antenna-delivered power for a 1-V RMS source."""

    load_parallel = 1.0 / (
        1.0 / load
        + _capacitor_admittance(
            omega,
            load_shunt_cap_pf,
            CAPACITOR_Q,
        )
    )
    series_impedance = _inductor_impedance(
        omega,
        series_inductor_nh,
        INDUCTOR_Q,
    )
    input_impedance = 1.0 / (
        1.0 / (load_parallel + series_impedance)
        + _capacitor_admittance(
            omega,
            input_shunt_cap_pf,
            CAPACITOR_Q,
        )
    )
    input_voltage = input_impedance / (50.0 + input_impedance)
    series_current = input_voltage / (series_impedance + load_parallel)
    load_voltage = series_current * load_parallel

    source_available_power = 1.0 / (4.0 * 50.0)
    accepted_power = np.abs(input_voltage) ** 2 * np.real(1.0 / input_impedance)
    antenna_power = np.abs(load_voltage) ** 2 * np.real(1.0 / load)
    return {
        "input_impedance": input_impedance,
        "accepted_fraction": accepted_power / source_available_power,
        "antenna_delivered_fraction": antenna_power / source_available_power,
        "network_efficiency": antenna_power / accepted_power,
    }


def _curve_summary(frequency: np.ndarray, curve_db: np.ndarray) -> dict[str, Any]:
    minimum_index = int(np.argmin(curve_db))
    center_index = int(np.argmin(np.abs(frequency - 3.5)))
    passing = np.where(curve_db <= -10.0)[0]
    return {
        "worst_case_db": float(np.max(curve_db)),
        "minimum_db": float(curve_db[minimum_index]),
        "minimum_frequency_ghz": float(frequency[minimum_index]),
        "at_3_5_ghz_db": float(curve_db[center_index]),
        "fraction_at_or_below_minus_10_db": float(np.mean(curve_db <= -10.0)),
        "pass_edges_ghz": (
            [float(frequency[passing[0]]), float(frequency[passing[-1]])]
            if len(passing)
            else []
        ),
    }


def _read_hfss_impedance(app: Hfss) -> tuple[np.ndarray, np.ndarray]:
    expression = f"St({TERMINAL},{TERMINAL})"
    data = app.post.get_solution_data(
        expressions=expression,
        setup_sweep_name=f"{SETUP_NAME} : {SWEEP_NAME}",
        report_category="Terminal Solution Data",
    )
    if not data:
        raise RuntimeError("The solved HFSS terminal sweep could not be loaded.")
    frequency, real = data.get_expression_data(expression, formula="real")
    _, imaginary = data.get_expression_data(expression, formula="imag")
    frequency = np.asarray(frequency, dtype=float)
    gamma = np.asarray(real, dtype=float) + 1j * np.asarray(imaginary, dtype=float)
    impedance = 50.0 * (1.0 + gamma) / (1.0 - gamma)
    order = np.argsort(frequency)
    return frequency[order], impedance[order]


def run(args: argparse.Namespace) -> int:
    project = args.project.resolve()
    if not project.is_file():
        raise FileNotFoundError(f"Solve the baseline project first: {project}")

    results_dir = project.parent / "results" / "n78_matching"
    results_dir.mkdir(parents=True, exist_ok=True)
    manifest_file = project.with_name(project.stem + "_matching_manifest.json")
    csv_file = results_dir / "matching_network_response.csv"
    plot_file = results_dir / "matching_network_response.png"

    app = Hfss(
        project=str(project),
        design=DESIGN_NAME,
        version=AEDT_VERSION,
        new_desktop=args.aedt_process_id is None,
        close_on_exit=False,
        student_version=True,
        aedt_process_id=args.aedt_process_id,
    )
    try:
        frequency, load = _read_hfss_impedance(app)
    finally:
        app.release_desktop(close_projects=False, close_desktop=False)

    omega = 2.0 * np.pi * frequency * 1e9
    baseline_db = _reflection_db(load)

    def ideal_objective(values: np.ndarray) -> float:
        impedance = _pi_input_impedance(
            load,
            omega,
            values[0],
            values[1],
            values[2],
            lossy=False,
        )
        return float(np.max(np.abs((impedance - 50.0) / (impedance + 50.0))))

    ideal_optimization = differential_evolution(
        ideal_objective,
        bounds=[(0.05, 5.0), (0.01, 5.0), (0.05, 5.0)],
        seed=17,
        tol=1e-9,
        popsize=24,
        maxiter=400,
        polish=True,
    )
    ideal_values = ideal_optimization.x
    ideal_db = _reflection_db(
        _pi_input_impedance(
            load,
            omega,
            ideal_values[0],
            ideal_values[1],
            ideal_values[2],
            lossy=False,
        )
    )

    capacitor_1_values = (1.8, 2.0, 2.2, 2.4, 2.7)
    inductor_values = (1.5, 1.6, 1.8, 2.0, 2.2)
    capacitor_2_values = (1.2, 1.3, 1.5, 1.6, 1.8, 2.0)
    tolerance_corners = np.asarray(
        [
            (c1, ind, c2)
            for c1 in (1.0 - TOLERANCE, 1.0 + TOLERANCE)
            for ind in (1.0 - TOLERANCE, 1.0 + TOLERANCE)
            for c2 in (1.0 - TOLERANCE, 1.0 + TOLERANCE)
        ]
    )
    robust_candidates: list[dict[str, Any]] = []
    for capacitor_1 in capacitor_1_values:
        for inductor in inductor_values:
            for capacitor_2 in capacitor_2_values:
                corner_worst_db = []
                for corner in tolerance_corners:
                    response = _reflection_db(
                        _pi_input_impedance(
                            load,
                            omega,
                            capacitor_1 * corner[0],
                            inductor * corner[1],
                            capacitor_2 * corner[2],
                            lossy=True,
                        )
                    )
                    corner_worst_db.append(float(np.max(response)))
                robust_candidates.append(
                    {
                        "load_shunt_capacitor_pf": capacitor_1,
                        "series_inductor_nh": inductor,
                        "input_shunt_capacitor_pf": capacitor_2,
                        "worst_tolerance_corner_db": max(corner_worst_db),
                    }
                )
    robust_choice = min(
        robust_candidates,
        key=lambda candidate: candidate["worst_tolerance_corner_db"],
    )
    standard_db = _reflection_db(
        _pi_input_impedance(
            load,
            omega,
            robust_choice["load_shunt_capacitor_pf"],
            robust_choice["series_inductor_nh"],
            robust_choice["input_shunt_capacitor_pf"],
            lossy=True,
        )
    )
    standard_power = _pi_power_metrics(
        load,
        omega,
        robust_choice["load_shunt_capacitor_pf"],
        robust_choice["series_inductor_nh"],
        robust_choice["input_shunt_capacitor_pf"],
    )

    rng = np.random.default_rng(20260727)
    component_scale = rng.uniform(
        1.0 - TOLERANCE,
        1.0 + TOLERANCE,
        size=(MONTE_CARLO_SAMPLES, 3),
    )
    load_2d = load[None, :]
    omega_2d = omega[None, :]
    monte_carlo_impedance = _pi_input_impedance(
        load_2d,
        omega_2d,
        robust_choice["load_shunt_capacitor_pf"] * component_scale[:, 0, None],
        robust_choice["series_inductor_nh"] * component_scale[:, 1, None],
        robust_choice["input_shunt_capacitor_pf"] * component_scale[:, 2, None],
        lossy=True,
    )
    monte_carlo_db = _reflection_db(monte_carlo_impedance)
    monte_carlo_worst_db = np.max(monte_carlo_db, axis=1)
    percentile_05, percentile_50, percentile_95 = np.percentile(
        monte_carlo_db,
        [5, 50, 95],
        axis=0,
    )

    with csv_file.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            [
                "frequency_ghz",
                "antenna_resistance_ohm",
                "antenna_reactance_ohm",
                "baseline_s11_db",
                "ideal_pi_s11_db",
                "standard_lossy_pi_s11_db",
                "monte_carlo_p05_s11_db",
                "monte_carlo_p50_s11_db",
                "monte_carlo_p95_s11_db",
            ]
        )
        for index, value in enumerate(frequency):
            writer.writerow(
                [
                    value,
                    load[index].real,
                    load[index].imag,
                    baseline_db[index],
                    ideal_db[index],
                    standard_db[index],
                    percentile_05[index],
                    percentile_50[index],
                    percentile_95[index],
                ]
            )

    plt.figure(figsize=(9.0, 5.2))
    plt.plot(frequency, baseline_db, label="HFSS antenna, unmatched", linewidth=2)
    plt.plot(frequency, ideal_db, label="Ideal optimized pi match", linewidth=2)
    plt.plot(
        frequency,
        standard_db,
        label="Standard lossy pi match (nominal)",
        linewidth=2,
    )
    plt.fill_between(
        frequency,
        percentile_05,
        percentile_95,
        color="tab:green",
        alpha=0.18,
        label="5th-95th percentile, +/-5% parts",
    )
    plt.axhline(-10.0, color="black", linestyle="--", linewidth=1.2, label="-10 dB target")
    plt.xlim(3.3, 3.8)
    plt.ylim(min(-35.0, float(np.min(ideal_db)) - 2.0), 0.0)
    plt.xlabel("Frequency (GHz)")
    plt.ylabel("S11 (dB)")
    plt.title("Velocity Connect n78 donor matching-network analysis")
    plt.grid(True, alpha=0.3)
    plt.legend(loc="lower left", fontsize=8)
    plt.tight_layout()
    plt.savefig(plot_file, dpi=180)
    plt.close()

    manifest = {
        "status": "complete",
        "completed_utc": datetime.now(timezone.utc).isoformat(),
        "project": str(project),
        "design": DESIGN_NAME,
        "hfss_solution": f"{SETUP_NAME} : {SWEEP_NAME}",
        "network_order_from_antenna_to_connector": [
            "shunt capacitor across antenna feed",
            "series inductor",
            "shunt capacitor at 50-ohm connector side",
        ],
        "baseline": _curve_summary(frequency, baseline_db),
        "ideal_pi_network": {
            "load_shunt_capacitor_pf": float(ideal_values[0]),
            "series_inductor_nh": float(ideal_values[1]),
            "input_shunt_capacitor_pf": float(ideal_values[2]),
            "response": _curve_summary(frequency, ideal_db),
        },
        "standard_component_network": {
            **robust_choice,
            "capacitor_q_at_3_5_ghz": CAPACITOR_Q,
            "inductor_q_at_3_5_ghz": INDUCTOR_Q,
            "nominal_response": _curve_summary(frequency, standard_db),
            "nominal_power_delivery": {
                "minimum_network_efficiency": float(
                    np.min(standard_power["network_efficiency"])
                ),
                "mean_network_efficiency": float(
                    np.mean(standard_power["network_efficiency"])
                ),
                "minimum_antenna_delivered_fraction_of_available_power": float(
                    np.min(standard_power["antenna_delivered_fraction"])
                ),
                "mean_antenna_delivered_fraction_of_available_power": float(
                    np.mean(standard_power["antenna_delivered_fraction"])
                ),
                "maximum_total_insertion_loss_db": float(
                    np.max(
                        -10.0
                        * np.log10(
                            standard_power["antenna_delivered_fraction"]
                        )
                    )
                ),
            },
            "tolerance": TOLERANCE,
        },
        "monte_carlo": {
            "samples": MONTE_CARLO_SAMPLES,
            "seed": 20260727,
            "uniform_component_tolerance": TOLERANCE,
            "probability_full_n78_at_or_below_minus_10_db": float(
                np.mean(monte_carlo_worst_db <= -10.0)
            ),
            "worst_band_s11_db_percentiles": {
                "p05": float(np.percentile(monte_carlo_worst_db, 5)),
                "p50": float(np.percentile(monte_carlo_worst_db, 50)),
                "p95": float(np.percentile(monte_carlo_worst_db, 95)),
            },
        },
        "csv": str(csv_file),
        "plot": str(plot_file),
        "physical_validation_required": True,
    }
    manifest_file.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Matching manifest: {manifest_file}")
    print(f"Response CSV: {csv_file}")
    print(f"Response plot: {plot_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))
