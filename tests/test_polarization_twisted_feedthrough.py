import math
import sys
import unittest
from pathlib import Path

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from polarization_twisted_feedthrough import (
    apply_differential_delay,
    ChannelScenario,
    donor_to_service_block,
    four_port_feedthrough,
    maximum_singular_value,
    relay_mode_matrix,
    select_em_minimax_delay,
    select_minimax_delay,
    straight_control_from_cross_blocks,
)


class PolarizationTwistedFeedthroughTest(unittest.TestCase):
    def test_four_port_is_reciprocal_and_passive(self):
        frequencies = np.asarray([3.3e9, 3.55e9, 3.8e9])
        matrices = four_port_feedthrough(
            frequencies,
            insertion_loss_db=1.0,
            return_loss_db=20.0,
            differential_delay_s=18e-12,
            topology="cross",
        )
        for matrix in matrices:
            np.testing.assert_allclose(matrix, matrix.T, atol=1e-12)
            self.assertLessEqual(maximum_singular_value(matrix), 1.0 + 1e-12)

    def test_cross_topology_uses_s41_and_s32(self):
        matrix = four_port_feedthrough(
            [3.55e9],
            insertion_loss_db=1.0,
            return_loss_db=20.0,
            topology="cross",
        )[0]
        self.assertGreater(abs(matrix[3, 0]), 0.8)
        self.assertGreater(abs(matrix[2, 1]), 0.8)
        self.assertEqual(abs(matrix[2, 0]), 0.0)
        self.assertEqual(abs(matrix[3, 1]), 0.0)

    def test_passivity_violation_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "passive"):
            four_port_feedthrough(
                [3.55e9],
                insertion_loss_db=0.0,
                return_loss_db=3.0,
            )

    def test_minimax_selection_matches_direct_brute_force(self):
        frequencies = np.asarray([3.3e9, 3.8e9])
        direct = np.stack([np.eye(2, dtype=complex) * 0.20] * 2)
        donor = np.stack([np.eye(2, dtype=complex) * 0.45] * 2)
        service = np.stack([np.eye(2, dtype=complex) * 0.45] * 2)
        scenario = ChannelScenario("declared-test", direct, donor, service)
        delays = [0.0, 25e-12, 50e-12]
        result = select_minimax_delay(
            frequencies,
            [scenario],
            delays,
            insertion_loss_db=1.0,
            topology="straight",
        )

        brute_force = []
        for delay in delays:
            worst = math.inf
            for index, frequency in enumerate(frequencies):
                feed = relay_mode_matrix(
                    frequency,
                    insertion_loss_db=1.0,
                    differential_delay_s=delay,
                    topology="straight",
                )
                composite = direct[index] + service[index] @ feed @ donor[index]
                worst = min(
                    worst,
                    float(np.linalg.svd(composite, compute_uv=False)[-1]),
                )
            brute_force.append(worst)
        expected = delays[int(np.argmax(brute_force))]
        self.assertEqual(result["selected_delay_s"], expected)

    def test_hfss_block_extraction_preserves_cross_port_order(self):
        matrices = four_port_feedthrough(
            [3.55e9],
            insertion_loss_db=0.8,
            return_loss_db=20.0,
            topology="cross",
        )
        block = donor_to_service_block(matrices)
        self.assertEqual(block.shape, (1, 2, 2))
        self.assertGreater(abs(block[0, 0, 1]), 0.8)  # S32
        self.assertGreater(abs(block[0, 1, 0]), 0.8)  # S41
        self.assertEqual(abs(block[0, 0, 0]), 0.0)  # S31
        self.assertEqual(abs(block[0, 1, 1]), 0.0)  # S42

    def test_em_selector_uses_exact_frequency_dependent_blocks(self):
        frequencies = np.asarray([3.3e9, 3.8e9])
        four_port = four_port_feedthrough(
            frequencies,
            insertion_loss_db=0.8,
            return_loss_db=20.0,
            topology="cross",
        )
        cross = donor_to_service_block(four_port)
        straight = straight_control_from_cross_blocks(cross)
        delayed = apply_differential_delay(frequencies, cross, 25e-12)
        self.assertFalse(np.allclose(cross[:, :, 1], delayed[:, :, 1]))
        np.testing.assert_allclose(cross[:, :, 0], delayed[:, :, 0])

        direct = np.stack([np.eye(2, dtype=complex) * 0.20] * 2)
        donor = np.stack([np.eye(2, dtype=complex) * 0.45] * 2)
        service = np.stack([np.eye(2, dtype=complex) * 0.45] * 2)
        scenario = ChannelScenario("em-test", direct, donor, service)
        result = select_em_minimax_delay(
            frequencies,
            [scenario],
            straight,
            [0.0, 25e-12, 50e-12],
            topology="straight-control",
        )
        self.assertEqual(
            result["objective"],
            "argmax_delay min_scenario,frequency "
            "sigma_min(H_direct + H_service F_HFSS,delay H_donor)",
        )
        self.assertEqual(len(result["evaluations"]), 3)


if __name__ == "__main__":
    unittest.main()
