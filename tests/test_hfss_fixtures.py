from pathlib import Path

import numpy as np
import skrf as rf


ROOT = Path(__file__).resolve().parents[1]
V4 = ROOT / "fixtures" / "hfss" / "PTF_V4_Balanced_Cross.s4p"
V5 = ROOT / "fixtures" / "hfss" / "PTF_V5_Delay25ps_Cross.s4p"


def _group_delay_ps(network: rf.Network, output_port: int, input_port: int) -> np.ndarray:
    phase = np.unwrap(np.angle(network.s[:, output_port, input_port]))
    return -np.gradient(phase, 2.0 * np.pi * network.f) * 1.0e12


def test_solved_four_port_fixtures_are_loadable_reciprocal_and_contractive() -> None:
    for path in (V4, V5):
        network = rf.Network(str(path))
        assert network.nports == 4
        assert network.f[0] == 3.3e9
        assert network.f[-1] == 3.8e9
        assert np.allclose(network.s, np.swapaxes(network.s, 1, 2), atol=1e-6)
        maximum_singular_value = np.linalg.svd(network.s, compute_uv=False)[:, 0]
        assert float(maximum_singular_value.max()) <= 1.0 + 1e-6
        assert float(np.abs(network.s[:, 3, 0]).min()) > 0.99
        assert float(np.abs(network.s[:, 2, 1]).min()) > 0.99


def test_physical_delay_fixture_realizes_declared_differential_delay() -> None:
    balanced = rf.Network(str(V4))
    delayed = rf.Network(str(V5))
    balanced_delta = _group_delay_ps(balanced, 3, 0) - _group_delay_ps(
        balanced, 2, 1
    )
    delayed_delta = _group_delay_ps(delayed, 3, 0) - _group_delay_ps(delayed, 2, 1)
    assert abs(float(np.mean(balanced_delta))) < 0.1
    assert 24.8 < abs(float(np.mean(delayed_delta))) < 25.1
    assert float(np.ptp(delayed_delta)) < 0.01
