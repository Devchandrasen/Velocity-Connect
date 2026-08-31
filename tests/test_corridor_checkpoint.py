import csv
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from verify_corridor_checkpoint import validate_corridor_checkpoint


LEDGER_FIELDS = [
    "run_id", "status", "error", "seed", "passive_model", "enable_handover",
    "use_ideal_rrc", "num_gnbs", "gnb_spacing_m", "handover_hysteresis_db",
    "handover_ttt_ms", "handover_attempts", "handover_successes",
    "handover_failures", "mean_handover_duration_ms", "mean_application_gap_ms",
]


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def make_checkpoint(root: Path, successes: int = 1) -> Path:
    ledger_rows = []
    for seed in (21, 22, 23):
        run_id = f"run_seed{seed}"
        raw = root / "raw" / run_id
        ledger_rows.append(
            {
                "run_id": run_id,
                "status": "ok",
                "error": "",
                "seed": seed,
                "passive_model": "component_budget",
                "enable_handover": 1,
                "use_ideal_rrc": 1,
                "num_gnbs": 3,
                "gnb_spacing_m": 1000,
                "handover_hysteresis_db": 1.5,
                "handover_ttt_ms": 128,
                "handover_attempts": successes,
                "handover_successes": successes,
                "handover_failures": 0,
                "mean_handover_duration_ms": 2.0,
                "mean_application_gap_ms": 6.0,
            }
        )
        event_rows = [
            {
                "imsi": 1,
                "source_cell_id": 1,
                "target_cell_id": 3,
                "final_cell_id": 3,
                "start_time_s": 1.0,
                "end_time_s": 1.002,
                "protocol_duration_ms": 2.0,
                "application_gap_ms": 6.0,
                "success": 1,
                "completed": 1,
            }
            for _ in range(successes)
        ]
        write_csv(
            raw / "handover_events.csv",
            [
                "imsi", "source_cell_id", "target_cell_id", "final_cell_id",
                "start_time_s", "end_time_s", "protocol_duration_ms",
                "application_gap_ms", "success", "completed",
            ],
            event_rows,
        )
        write_csv(
            raw / "ue_serving_cells.csv",
            ["imsi", "initial_cell_id", "final_cell_id", "changed"],
            [{"imsi": 1, "initial_cell_id": 1, "final_cell_id": 3, "changed": 1}],
        )
        write_csv(
            raw / "rsrp_measurements.csv",
            [
                "time_s", "imsi", "serving_cell_id", "serving_rsrp_code",
                "serving_rsrp_dbm", "neighbour_cell_id",
                "neighbour_rsrp_code", "neighbour_rsrp_dbm", "has_neighbour",
            ],
            [{
                "time_s": 1.0,
                "imsi": 1,
                "serving_cell_id": 1,
                "serving_rsrp_code": 31,
                "serving_rsrp_dbm": -109,
                "neighbour_cell_id": 3,
                "neighbour_rsrp_code": 33,
                "neighbour_rsrp_dbm": -107,
                "has_neighbour": 1,
            }],
        )

    ledger = root / "campaign_runs.csv"
    write_csv(ledger, LEDGER_FIELDS, ledger_rows)
    return ledger


class CorridorCheckpointTest(unittest.TestCase):
    def test_accepts_complete_protocol_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            results = validate_corridor_checkpoint(make_checkpoint(Path(tmp)))
        self.assertEqual([result["seed"] for result in results], [21, 22, 23])
        self.assertTrue(all(result["handover_successes"] == 1 for result in results))

    def test_rejects_zero_handover_successes(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = make_checkpoint(Path(tmp), successes=0)
            with self.assertRaisesRegex(ValueError, "recorded no successful handover"):
                validate_corridor_checkpoint(ledger)

    def test_rejects_missing_neighbour_measurement(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ledger = make_checkpoint(root)
            write_csv(
                root / "raw" / "run_seed22" / "rsrp_measurements.csv",
                [
                    "time_s", "imsi", "serving_cell_id", "serving_rsrp_code",
                    "serving_rsrp_dbm", "neighbour_cell_id",
                    "neighbour_rsrp_code", "neighbour_rsrp_dbm", "has_neighbour",
                ],
                [],
            )
            with self.assertRaisesRegex(ValueError, "no neighbour-RSRP"):
                validate_corridor_checkpoint(ledger)


if __name__ == "__main__":
    unittest.main()
