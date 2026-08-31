from types import SimpleNamespace

import numpy as np
import skrf as rf

from hardware.analyze_vna_touchstone import analyze


def _args() -> SimpleNamespace:
    return SimpleNamespace(
        band_start_ghz=3.3,
        band_stop_ghz=3.8,
        match_gate_db=-10.0,
        isolation_gate_db=-18.0,
        tarc_gate_db=-10.0,
        phase_step_deg=5.0,
        through_gate_db=-3.0,
        cross_coupling_gate_db=-20.0,
        amplitude_imbalance_gate_db=0.5,
        group_delay_imbalance_gate_ns=0.5,
    )


def test_two_port_measurement_summary_passes_declared_gates() -> None:
    frequency = rf.Frequency.from_f([3.3, 3.55, 3.8], unit="ghz")
    s = np.zeros((3, 2, 2), dtype=complex)
    s[:, 0, 0] = 0.1
    s[:, 1, 1] = 0.1
    s[:, 0, 1] = 0.04
    s[:, 1, 0] = 0.04
    network = rf.Network(frequency=frequency, s=s, z0=50)

    summary, rows = analyze(network, _args())

    assert len(rows) == 3
    assert summary["measurement_type"] == "two_port_donor"
    assert summary["worst_s11_db"] == -20.0
    assert summary["worst_s12_db"] < -18.0
    assert summary["maximum_s_parameter_ecc"] >= 0.0
    assert summary["all_gates_pass"] is True


def test_four_port_measurement_summary_checks_paths_and_delay() -> None:
    frequency_hz = np.array([3.3e9, 3.55e9, 3.8e9])
    frequency = rf.Frequency.from_f(frequency_hz, unit="hz")
    s = np.zeros((3, 4, 4), dtype=complex)
    delay_31_s = 1.0e-9
    delay_42_s = 1.2e-9
    s[:, 2, 0] = 0.80 * np.exp(-1j * 2.0 * np.pi * frequency_hz * delay_31_s)
    s[:, 3, 1] = 0.77 * np.exp(-1j * 2.0 * np.pi * frequency_hz * delay_42_s)
    for row, column in ((2, 1), (3, 0), (2, 3), (3, 2)):
        s[:, row, column] = 0.03
    network = rf.Network(frequency=frequency, s=s, z0=50)

    summary, rows = analyze(network, _args())

    assert len(rows) == 3
    assert summary["measurement_type"] == "four_port_passive_feedthrough"
    assert summary["worst_s31_db"] > -3.0
    assert summary["maximum_cross_coupling_db"] < -20.0
    assert summary["maximum_group_delay_imbalance_ns"] < 0.5
    assert summary["all_gates_pass"] is True


def test_two_port_nonphysical_ecc_denominator_is_reported_not_serialized_as_nan() -> None:
    frequency = rf.Frequency.from_f([3.55], unit="ghz")
    s = np.ones((1, 2, 2), dtype=complex)
    network = rf.Network(frequency=frequency, s=s, z0=50)

    summary, rows = analyze(network, _args())

    assert rows[0]["ecc_s_parameter"] is None
    assert summary["maximum_s_parameter_ecc"] is None
    assert summary["invalid_s_parameter_ecc_sample_count"] == 1
