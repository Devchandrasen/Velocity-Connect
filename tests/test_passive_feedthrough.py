import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from calibrate_passive_model import calibrate
from passive_feedthrough import PassiveBudget, budget_from_measurement


class PassiveFeedthroughTest(unittest.TestCase):
    def test_component_equation_counts_indoor_loss_once(self):
        budget = PassiveBudget(
            feeder_loss_db=3,
            coupling_loss_db=8,
            indoor_path_loss_db=4,
            donor_gain_dbi=8,
            service_gain_dbi=2,
        )
        budget.validate()
        self.assertEqual(budget.network_loss_db, 11)
        self.assertEqual(budget.aperture_gain_db, 10)
        self.assertEqual(budget.equivalent_loss_db, 5)

    def test_net_gain_is_rejected_by_system_level_abstraction(self):
        budget = PassiveBudget(1, 1, 1, 8, 2)
        with self.assertRaisesRegex(ValueError, "net gain"):
            budget.validate()

    def test_positive_passive_s21_is_rejected(self):
        row = {
            "sample_id": "bad",
            "frequency_hz": "3500000000",
            "feeder_s21_db": "1",
            "feedthrough_s21_db": "-2",
            "coupling_loss_db": "1",
            "indoor_path_loss_db": "4",
            "donor_gain_dbi": "8",
            "service_gain_dbi": "2",
        }
        with self.assertRaisesRegex(ValueError, "S21"):
            budget_from_measurement(row)

    def test_calibration_writes_auditable_outputs(self):
        rows = [
            {
                "sample_id": "vna-001",
                "frequency_hz": "3500000000",
                "feeder_s21_db": "-3",
                "feedthrough_s21_db": "-6",
                "coupling_loss_db": "2",
                "indoor_path_loss_db": "4",
                "donor_gain_dbi": "8",
                "service_gain_dbi": "2",
            },
            {
                "sample_id": "vna-002",
                "frequency_hz": "3510000000",
                "feeder_s21_db": "-3.2",
                "feedthrough_s21_db": "-6.1",
                "coupling_loss_db": "2",
                "indoor_path_loss_db": "4.5",
                "donor_gain_dbi": "8",
                "service_gain_dbi": "2",
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "measurements.csv"
            with source.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
            summary = calibrate(source, root / "out")
            with (root / "out" / "calibrated_component_samples.csv").open(
                encoding="utf-8"
            ) as handle:
                calibrated = list(csv.DictReader(handle))
            persisted = json.loads(
                (root / "out" / "calibration_summary.json").read_text(
                    encoding="utf-8"
                )
            )
        self.assertEqual(summary["n_samples"], 2)
        self.assertEqual(len(calibrated), 2)
        self.assertFalse(persisted["synthetic_measurements_used"])
        self.assertAlmostEqual(float(calibrated[0]["equivalent_loss_db"]), 5.0)
