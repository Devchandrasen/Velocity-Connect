import sys
import unittest
from pathlib import Path

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from rf_feasibility import (
    PUBLICATION_CORNERS,
    is_passive,
    maximum_singular_value,
    reciprocal_two_port,
)


class RfFeasibilityTest(unittest.TestCase):
    def test_publication_corners_are_valid_and_ordered(self):
        for corner in PUBLICATION_CORNERS:
            corner.validate()
        losses = [corner.equivalent_loss_db for corner in PUBLICATION_CORNERS]
        self.assertEqual(losses, sorted(losses))
        self.assertAlmostEqual(PUBLICATION_CORNERS[1].equivalent_loss_db, 6.455)

    def test_break_even_equation(self):
        nominal = PUBLICATION_CORNERS[1]
        self.assertAlmostEqual(
            nominal.break_even_network_loss_db(20.0),
            22.545,
        )
        self.assertGreater(
            nominal.break_even_network_loss_db(20.0),
            nominal.network_loss_db,
        )

    def test_declared_two_port_is_passive(self):
        for corner in PUBLICATION_CORNERS:
            matrix = reciprocal_two_port(
                return_loss_db=15.233,
                insertion_loss_db=corner.network_loss_db,
            )
            self.assertTrue(is_passive(matrix))
            self.assertLess(maximum_singular_value(matrix), 1.0)

    def test_active_matrix_is_rejected(self):
        active = np.asarray([[0.0, 1.1], [1.1, 0.0]], dtype=complex)
        self.assertFalse(is_passive(active))


if __name__ == "__main__":
    unittest.main()
