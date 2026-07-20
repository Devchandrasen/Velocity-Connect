import math
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from research_campaign import (
    aggregate_rows,
    build_parser,
    build_simulation_command,
    parse_csv_list,
    resolve_profile,
)
from verify_paper_checkpoint import validate_checkpoint


class CampaignHelpersTest(unittest.TestCase):
    def test_parse_csv_list_rejects_empty_items(self):
        with self.assertRaises(ValueError):
            parse_csv_list("1,,3", int)

    def test_build_command_is_shell_free_and_parameterized(self):
        command = build_simulation_command(
            "./ns3", "hsr_velocity_connect", "repeater", 300.0, 500.0, 2, 7, 11,
            Path("out/raw/run_001"),
        )
        self.assertEqual(command[:2], ["./ns3", "run"])
        self.assertEqual(len(command), 3)
        self.assertIn("--singleRun=1", command[2])
        self.assertIn("hsr_velocity_connect", command[2])
        self.assertIn("--scenario=repeater", command[2])
        self.assertIn("--seed=7", command[2])
        self.assertIn("--numUes=2", command[2])
        self.assertIn("--saturatingLoad=1", command[2])

    def test_paper_profile_matches_submitted_workload(self):
        args = build_parser().parse_args(["--profile", "paper"])
        profile = resolve_profile(args)
        self.assertEqual(profile["num_ues"], 10)
        self.assertEqual(profile["app_pkt_size"], 1024)
        self.assertFalse(profile["saturating_load"])
        self.assertAlmostEqual(profile["per_ue_offered_mbps"], 8.19)

    def test_paper_command_carries_reproducibility_parameters(self):
        command = build_simulation_command(
            "./ns3", "hsr_velocity_connect", "repeater", 300.0, 1500.0, 10, 3, 9,
            Path("out/raw/paper"), sim_time=2.0, app_start=0.2,
            app_pkt_size=1024, saturating_load=False,
            per_ue_offered_mbps=8.19, paper_profile=True,
        )
        self.assertIn("--appPktSize=1024", command[2])
        self.assertIn("--saturatingLoad=0", command[2])
        self.assertIn("--paperProfile=1", command[2])

    def test_aggregate_rows_reports_mean_sd_and_ci(self):
        rows = [
            {
                "scenario": "repeater", "speed_kmph": "300", "distance_m": "500",
                "num_ues": "1", "throughput_mbps": "10", "pdr": "1",
                "mean_lat_ms": "2", "p95_lat_ms": "4", "jain_fairness": "0",
            },
            {
                "scenario": "repeater", "speed_kmph": "300", "distance_m": "500",
                "num_ues": "1", "throughput_mbps": "14", "pdr": "0.9",
                "mean_lat_ms": "4", "p95_lat_ms": "8", "jain_fairness": "0",
            },
        ]
        summary = aggregate_rows(rows)[0]
        self.assertEqual(summary["n_runs"], 2)
        self.assertAlmostEqual(summary["throughput_mbps_mean"], 12.0)
        self.assertAlmostEqual(summary["throughput_mbps_std"], math.sqrt(8.0))
        self.assertGreater(summary["throughput_mbps_ci95"], 0.0)
        self.assertEqual(summary["pdr_n"], 2)

    def test_paper_checkpoint_rejects_failed_scenario(self):
        rows = [
            ("metal", "failed", "scheduler assertion", "", "", "", ""),
            ("composite", "ok", "", "1.0", "0.5", "2.0", "3.0"),
            ("repeater", "ok", "", "8.0", "0.9", "2.0", "3.0"),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "campaign_runs.csv"
            ledger.write_text(
                "scenario,status,error,throughput_mbps,pdr,mean_lat_ms,p95_lat_ms\n"
                + "".join(",".join(row) + "\n" for row in rows),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "metal checkpoint failed"):
                validate_checkpoint(ledger)

    def test_paper_checkpoint_accepts_consistent_zero_reception_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "campaign_runs.csv"
            ledger.write_text(
                "scenario,status,error,throughput_mbps,pdr,mean_lat_ms,p95_lat_ms\n"
                "metal,ok,,0.0,0.0,nan,nan\n"
                "composite,ok,,2.0,0.5,3.0,4.0\n"
                "repeater,ok,,8.0,0.9,2.0,3.0\n",
                encoding="utf-8",
            )
            results = validate_checkpoint(ledger)
        self.assertEqual(set(results), {"metal", "composite", "repeater"})
        self.assertIsNone(results["metal"]["mean_lat_ms"])
        self.assertEqual(results["repeater"]["throughput_mbps"], 8.0)


if __name__ == "__main__":
    unittest.main()
