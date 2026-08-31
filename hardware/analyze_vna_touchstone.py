"""Analyze measured two-port or four-port Velocity Connect Touchstone data."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import skrf as rf


def _db(value: np.ndarray | float) -> np.ndarray | float:
    return 20.0 * np.log10(np.maximum(np.abs(value), 1e-15))


def _s_parameter_ecc(matrix: np.ndarray) -> float | None:
    s11, s12 = matrix[0, 0], matrix[0, 1]
    s21, s22 = matrix[1, 0], matrix[1, 1]
    numerator = abs(np.conj(s11) * s12 + np.conj(s21) * s22) ** 2
    accepted_1 = 1.0 - abs(s11) ** 2 - abs(s21) ** 2
    accepted_2 = 1.0 - abs(s22) ** 2 - abs(s12) ** 2
    if accepted_1 <= 0 or accepted_2 <= 0:
        return None
    denominator = accepted_1 * accepted_2
    return float(numerator / denominator)


def _worst_phase_tarc(matrix: np.ndarray, phase_step_deg: float) -> tuple[float, float]:
    phases = np.arange(0.0, 360.0, phase_step_deg)
    phase_factor = np.exp(1j * np.deg2rad(phases))
    reflected_1 = matrix[0, 0] + matrix[0, 1] * phase_factor
    reflected_2 = matrix[1, 0] + matrix[1, 1] * phase_factor
    tarc = np.sqrt((np.abs(reflected_1) ** 2 + np.abs(reflected_2) ** 2) / 2.0)
    index = int(np.argmax(tarc))
    return float(_db(tarc[index])), float(phases[index])


def _group_delay_ns(frequency_hz: np.ndarray, values: np.ndarray) -> np.ndarray:
    phase = np.unwrap(np.angle(values))
    return -1e9 * np.gradient(phase, 2.0 * np.pi * frequency_hz)


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze measured Velocity Connect .s2p or .s4p data."
    )
    parser.add_argument("touchstone", type=Path)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-csv", type=Path)
    parser.add_argument("--band-start-ghz", type=float, default=3.3)
    parser.add_argument("--band-stop-ghz", type=float, default=3.8)
    parser.add_argument("--match-gate-db", type=float, default=-10.0)
    parser.add_argument("--isolation-gate-db", type=float, default=-18.0)
    parser.add_argument("--tarc-gate-db", type=float, default=-10.0)
    parser.add_argument("--phase-step-deg", type=float, default=5.0)
    parser.add_argument("--through-gate-db", type=float, default=-3.0)
    parser.add_argument("--cross-coupling-gate-db", type=float, default=-20.0)
    parser.add_argument("--amplitude-imbalance-gate-db", type=float, default=0.5)
    parser.add_argument("--group-delay-imbalance-gate-ns", type=float, default=0.5)
    return parser.parse_args()


def analyze(network: rf.Network, args: argparse.Namespace) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if network.nports not in (2, 4):
        raise ValueError("Only two-port and four-port Touchstone files are supported.")
    frequency_ghz = network.f / 1e9
    mask = (
        (frequency_ghz >= args.band_start_ghz - 1e-12)
        & (frequency_ghz <= args.band_stop_ghz + 1e-12)
    )
    if not np.any(mask):
        raise ValueError("Touchstone data contain no samples in the requested band.")
    frequency_hz = network.f[mask]
    frequency_ghz = frequency_ghz[mask]
    s = network.s[mask]
    rows: list[dict[str, Any]] = []

    if network.nports == 2:
        for index, freq in enumerate(frequency_ghz):
            matrix = s[index]
            tarc_db, tarc_phase = _worst_phase_tarc(
                matrix, args.phase_step_deg
            )
            rows.append(
                {
                    "frequency_ghz": float(freq),
                    "s11_db": float(_db(matrix[0, 0])),
                    "s22_db": float(_db(matrix[1, 1])),
                    "s12_db": float(_db(matrix[0, 1])),
                    "s21_db": float(_db(matrix[1, 0])),
                    "worst_phase_tarc_db": tarc_db,
                    "worst_phase_tarc_deg": tarc_phase,
                    "ecc_s_parameter": _s_parameter_ecc(matrix),
                }
            )
        valid_ecc = [
            row["ecc_s_parameter"]
            for row in rows
            if row["ecc_s_parameter"] is not None
        ]
        summary = {
            "measurement_type": "two_port_donor",
            "worst_s11_db": max(row["s11_db"] for row in rows),
            "worst_s22_db": max(row["s22_db"] for row in rows),
            "worst_s12_db": max(row["s12_db"] for row in rows),
            "worst_s21_db": max(row["s21_db"] for row in rows),
            "worst_phase_tarc_db": max(
                row["worst_phase_tarc_db"] for row in rows
            ),
            "maximum_s_parameter_ecc": max(valid_ecc) if valid_ecc else None,
            "invalid_s_parameter_ecc_sample_count": len(rows) - len(valid_ecc),
        }
        gates = {
            "s11": summary["worst_s11_db"] <= args.match_gate_db,
            "s22": summary["worst_s22_db"] <= args.match_gate_db,
            "s12": summary["worst_s12_db"] <= args.isolation_gate_db,
            "s21": summary["worst_s21_db"] <= args.isolation_gate_db,
            "tarc": summary["worst_phase_tarc_db"] <= args.tarc_gate_db,
        }
    else:
        through_31 = s[:, 2, 0]
        through_42 = s[:, 3, 1]
        through_31_db = _db(through_31)
        through_42_db = _db(through_42)
        delay_31_ns = _group_delay_ns(frequency_hz, through_31)
        delay_42_ns = _group_delay_ns(frequency_hz, through_42)
        cross_pairs = {
            "s32": s[:, 2, 1],
            "s41": s[:, 3, 0],
            "s34": s[:, 2, 3],
            "s43": s[:, 3, 2],
        }
        for index, freq in enumerate(frequency_ghz):
            row = {
                "frequency_ghz": float(freq),
                "s31_db": float(through_31_db[index]),
                "s42_db": float(through_42_db[index]),
                "through_amplitude_imbalance_db": float(
                    abs(through_31_db[index] - through_42_db[index])
                ),
                "group_delay_s31_ns": float(delay_31_ns[index]),
                "group_delay_s42_ns": float(delay_42_ns[index]),
                "group_delay_imbalance_ns": float(
                    abs(delay_31_ns[index] - delay_42_ns[index])
                ),
            }
            for name, values in cross_pairs.items():
                row[f"{name}_db"] = float(_db(values[index]))
            rows.append(row)
        summary = {
            "measurement_type": "four_port_passive_feedthrough",
            "worst_s31_db": min(row["s31_db"] for row in rows),
            "worst_s42_db": min(row["s42_db"] for row in rows),
            "maximum_through_amplitude_imbalance_db": max(
                row["through_amplitude_imbalance_db"] for row in rows
            ),
            "maximum_group_delay_imbalance_ns": max(
                row["group_delay_imbalance_ns"] for row in rows
            ),
            "maximum_cross_coupling_db": max(
                row[f"{name}_db"]
                for row in rows
                for name in cross_pairs
            ),
        }
        gates = {
            "s31": summary["worst_s31_db"] >= args.through_gate_db,
            "s42": summary["worst_s42_db"] >= args.through_gate_db,
            "through_amplitude_imbalance": (
                summary["maximum_through_amplitude_imbalance_db"]
                <= args.amplitude_imbalance_gate_db
            ),
            "group_delay_imbalance": (
                summary["maximum_group_delay_imbalance_ns"]
                <= args.group_delay_imbalance_gate_ns
            ),
            "cross_coupling": (
                summary["maximum_cross_coupling_db"]
                <= args.cross_coupling_gate_db
            ),
        }
    summary["gates"] = gates
    summary["all_gates_pass"] = all(gates.values())
    return summary, rows


def main() -> None:
    args = _parse_args()
    source = args.touchstone.resolve()
    if not source.exists():
        raise FileNotFoundError(source)
    if not 0.1 <= args.phase_step_deg <= 30.0:
        raise ValueError("phase-step-deg must be within 0.1-30 degrees.")

    network = rf.Network(str(source))
    summary, rows = analyze(network, args)
    payload = {
        "status": "complete",
        "evidence_class": "measured_touchstone",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "source": str(source),
        "source_sha256": _hash(source),
        "ports": network.nports,
        "band_ghz": [args.band_start_ghz, args.band_stop_ghz],
        "sample_count": len(rows),
        "summary": summary,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(payload, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    if args.output_csv:
        args.output_csv.parent.mkdir(parents=True, exist_ok=True)
        with args.output_csv.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    print(json.dumps(summary, indent=2, allow_nan=False))
    print(f"Evidence: {args.output_json.resolve()}")


if __name__ == "__main__":
    main()
