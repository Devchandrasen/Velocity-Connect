"""Coordinate-aware field integration and fail-closed passive power accounting.

No efficiency is clipped. Loss-based efficiency is only a diagnostic: it cannot
override an inconsistent accepted-power budget or a failed input-power bound.
"""
from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
from scipy.integrate import simpson


def integrate_far_field(rows: Sequence[dict], *, angle_unit: str) -> dict:
    """Integrate explicit theta/phi rows, never infer flattened export ordering."""
    if angle_unit not in {"deg", "rad"} or not rows:
        raise ValueError("Explicit deg/rad units and nonempty field rows required")
    scale = math.pi / 180 if angle_unit == "deg" else 1.0
    coords = [(float(row["theta"]) * scale, float(row["phi"]) * scale) for row in rows]
    theta = np.unique([p[0] for p in coords])
    phi = np.unique([p[1] for p in coords])
    if len(theta) < 3 or len(phi) < 3 or len(rows) != len(theta) * len(phi):
        raise ValueError("Complete Cartesian angular grid required")
    if not (math.isclose(theta[0], 0, abs_tol=1e-9) and
            math.isclose(theta[-1], math.pi, abs_tol=1e-9) and
            math.isclose(phi[-1] - phi[0], 2 * math.pi, abs_tol=1e-9)):
        raise ValueError("Full-sphere support required")
    e_theta = np.empty((len(phi), len(theta)), dtype=complex)
    e_phi = np.empty_like(e_theta)
    visited = set()
    for row, (t, p) in zip(rows, coords):
        if not all(math.isfinite(v) for v in (t, p)) or (t, p) in visited:
            raise ValueError("Nonfinite or duplicated angular coordinates")
        visited.add((t, p))
        i, j = int(np.searchsorted(phi, p)), int(np.searchsorted(theta, t))
        a = complex(row["etheta_re"], row["etheta_im"])
        b = complex(row["ephi_re"], row["ephi_im"])
        if not all(math.isfinite(v) for v in (a.real, a.imag, b.real, b.imag)):
            raise ValueError("Nonfinite complex field")
        e_theta[i, j], e_phi[i, j] = a, b
    intensity = (np.abs(e_theta)**2 + np.abs(e_phi)**2) / (2 * 376.730313668)
    weighted = intensity * np.sin(theta)[None, :]
    primary = float(simpson(simpson(weighted, x=theta, axis=1), x=phi))
    crosscheck = float(np.trapezoid(np.trapezoid(weighted, x=theta, axis=1), x=phi))
    peak = max(float(np.max(np.abs(e_theta))), float(np.max(np.abs(e_phi))))
    seam = max(float(np.max(np.abs(e_theta[0] - e_theta[-1]))),
               float(np.max(np.abs(e_phi[0] - e_phi[-1]))))
    return {"radiated_power_w": primary, "trapezoid_power_w": crosscheck,
            "relative_quadrature_difference": abs(primary - crosscheck) / primary if primary > 0 else None,
            "relative_periodic_seam_difference": seam / peak if peak else 0.0,
            "theta_samples": len(theta), "phi_samples": len(phi),
            "ordering": "explicit_coordinates", "phasor_convention": "peak"}


def assess_power_budget(record: dict, *, closure_tolerance: float = 0.005) -> dict:
    """Necessary checks only. Passing does not establish mesh independence."""
    if not 0 < closure_tolerance <= 0.01:
        raise ValueError("Declare a power-closure tolerance in (0, 0.01]")
    keys = ("incident_w", "accepted_w", "native_radiated_w", "field_radiated_w",
            "conductor_loss_w", "dielectric_loss_w")
    values = {}
    for key in keys:
        v = record.get(key)
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
            raise ValueError(f"Missing/nonfinite independent power term: {key}")
        values[key] = float(v)
    if any(v < 0 for v in values.values()) or values["accepted_w"] <= 0 or values["incident_w"] <= 0:
        raise ValueError("Nonnegative powers and positive accepted/incident power required")
    contexts = [record.get(key) for key in ("native_context", "field_context", "loss_context")]
    if any(not isinstance(c, str) or not c for c in contexts) or len(set(contexts)) != 1:
        raise ValueError("Native, field and loss powers require the same explicit excitation context")
    pin, pacc, prad, pff, pc, pd = (values[k] for k in keys)
    closure = (prad + pc + pd - pacc) / pacc
    field_difference = (pff - prad) / pacc
    failures = []
    if pacc > pin * (1 + 1e-9):
        failures.append("accepted_exceeds_incident")
    if prad > pacc * (1 + 1e-9) or pff > pacc * (1 + 1e-9):
        failures.append("radiated_exceeds_accepted")
    if abs(closure) > closure_tolerance:
        failures.append("input_power_closure")
    if abs(field_difference) > closure_tolerance:
        failures.append("native_vs_field_power")
    return {"necessary_checks_pass": not failures, "failures": failures,
            "native_efficiency": prad / pacc, "field_efficiency": pff / pacc,
            "loss_based_efficiency_diagnostic": prad / (prad + pc + pd) if prad + pc + pd > 0 else None,
            "relative_input_closure_residual": closure,
            "relative_native_field_difference": field_difference,
            "closure_tolerance": closure_tolerance,
            "loss_based_ratio_overrides_raw_failure": False, "values_clipped": False,
            "mesh_independence_demonstrated": False, "independent_solver_validation": False}
