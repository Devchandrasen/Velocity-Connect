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
    validate_profile,
)
from verify_paper_checkpoint import validate_checkpoint
from statistical_evidence import t_critical_95


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
        self.assertIn("--gnbHeightM=10", command[2])
        self.assertIn("--gnbLateralOffsetM=0", command[2])
        self.assertIn("--ueHeightM=1.5", command[2])
        self.assertIn("hsr_velocity_connect", command[2])
        self.assertIn("--scenario=repeater", command[2])
        self.assertIn("--seed=7", command[2])
        self.assertIn("--numUes=2", command[2])
        self.assertIn("--numerology=0", command[2])
        self.assertIn("--saturatingLoad=1", command[2])
        self.assertIn("--passiveModel=component_budget", command[2])
        self.assertIn("--numGnbs=1", command[2])
        self.assertIn("--enableHandover=0", command[2])
        self.assertIn("--guardedCorridor=0", command[2])
        self.assertIn("--channelUpdatePeriodMs=0", command[2])
        self.assertIn("--enableSrs=0", command[2])
        self.assertIn("--declaredPassiveLossDb=6.5", command[2])
        self.assertIn("--donorGainDbi=8", command[2])
        self.assertIn("--serviceGainDbi=2", command[2])
        self.assertIn("--feederCableLossDb=3", command[2])
        self.assertIn("--indoorDistribLossDb=4", command[2])
        self.assertIn("--couplingLossDb=8", command[2])
        self.assertIn("--gnbTxPowerDbm=40", command[2])
        self.assertIn("--ueTxPowerDbm=23", command[2])

    def test_paper_profile_matches_submitted_workload(self):
        args = build_parser().parse_args(["--profile", "paper"])
        profile = resolve_profile(args)
        self.assertEqual(profile["num_ues"], 10)
        self.assertEqual(profile["numerology"], 1)
        self.assertEqual(profile["app_pkt_size"], 1024)
        self.assertFalse(profile["saturating_load"])
        self.assertAlmostEqual(profile["per_ue_offered_mbps"], 8.19)
        self.assertEqual(profile["passive_model"], "legacy_scalar")
        self.assertFalse(profile["enable_handover"])
        self.assertTrue(profile["use_ideal_rrc"])
        self.assertEqual(profile["legacy_repeater_loss_db"], 5.0)
        self.assertEqual(profile["gnb_tx_power_dbm"], 40.0)
        self.assertEqual(profile["ue_tx_power_dbm"], 23.0)

    def test_tx_power_overrides_are_carried_to_both_link_directions(self):
        args = build_parser().parse_args(
            [
                "--profile",
                "corridor",
                "--gnb-tx-power-dbm",
                "37",
                "--ue-tx-power-dbm",
                "20",
            ]
        )
        profile = resolve_profile(args)
        self.assertEqual(profile["gnb_tx_power_dbm"], 37.0)
        self.assertEqual(profile["ue_tx_power_dbm"], 20.0)
        command = build_simulation_command(
            "./ns3",
            "hsr_velocity_connect",
            "repeater",
            500.0,
            100.0,
            10,
            1,
            1,
            Path("out/raw/reciprocal"),
            gnb_tx_power_dbm=float(profile["gnb_tx_power_dbm"]),
            ue_tx_power_dbm=float(profile["ue_tx_power_dbm"]),
        )
        self.assertIn("--gnbTxPowerDbm=37", command[2])
        self.assertIn("--ueTxPowerDbm=20", command[2])

    def test_corridor_profile_enables_real_handover_configuration(self):
        args = build_parser().parse_args(["--profile", "corridor"])
        profile = resolve_profile(args)
        self.assertEqual(profile["num_gnbs"], 3)
        self.assertEqual(profile["gnb_height_m"], 10.0)
        self.assertEqual(profile["gnb_lateral_offset_m"], 10.0)
        self.assertEqual(profile["channel_update_period_ms"], 5.0)
        self.assertEqual(profile["ue_height_m"], 1.5)
        self.assertTrue(profile["enable_handover"])
        self.assertEqual(profile["passive_model"], "component_budget")
        self.assertTrue(profile["use_ideal_rrc"])
        command = build_simulation_command(
            "./ns3",
            "hsr_velocity_connect",
            "repeater",
            500.0,
            100.0,
            10,
            1,
            1,
            Path("out/raw/corridor"),
            num_gnbs=int(profile["num_gnbs"]),
            enable_handover=bool(profile["enable_handover"]),
            passive_model=str(profile["passive_model"]),
        )
        self.assertIn("--numGnbs=3", command[2])
        self.assertIn("--enableHandover=1", command[2])

    def test_guarded_corridor_requires_six_sites(self):
        args = build_parser().parse_args(
            ["--profile", "corridor", "--guarded-corridor", "1"]
        )
        with self.assertRaisesRegex(ValueError, "at least six"):
            validate_profile(resolve_profile(args))

    def test_guarded_corridor_command_records_spatial_contract(self):
        command = build_simulation_command(
            "./ns3",
            "hsr_velocity_connect",
            "repeater",
            500.0,
            0.0,
            1,
            1,
            1,
            Path("out/raw/guarded"),
            num_gnbs=6,
            gnb_lateral_offset_m=10.0,
            gnb_spacing_m=500.0,
            guarded_corridor=True,
            channel_update_period_ms=5.0,
        )
        self.assertIn("--numGnbs=6", command[2])
        self.assertIn("--guardedCorridor=1", command[2])
        self.assertIn("--gnbLateralOffsetM=10", command[2])
        self.assertIn("--channelUpdatePeriodMs=5", command[2])

    def test_component_profile_rejects_net_passive_gain(self):
        args = build_parser().parse_args(
            [
                "--profile", "corridor",
                "--feeder-cable-loss-db", "0",
                "--coupling-loss-db", "0",
                "--indoor-distrib-loss-db", "0",
                "--donor-gain-dbi", "8",
                "--service-gain-dbi", "2",
            ]
        )
        with self.assertRaisesRegex(ValueError, "net passive gain"):
            validate_profile(resolve_profile(args))

    def test_declared_scalar_profile_carries_only_explicit_loss_hypothesis(self):
        args = build_parser().parse_args(
            [
                "--profile",
                "corridor",
                "--passive-model",
                "declared_scalar",
                "--declared-passive-loss-db",
                "6.5",
            ]
        )
        profile = resolve_profile(args)
        validate_profile(profile)
        self.assertEqual(profile["passive_model"], "declared_scalar")
        self.assertEqual(profile["declared_passive_loss_db"], 6.5)
        command = build_simulation_command(
            "./ns3",
            "hsr_velocity_connect",
            "repeater",
            500.0,
            0.0,
            1,
            1,
            1,
            Path("out/raw/declared"),
            passive_model=str(profile["passive_model"]),
            declared_passive_loss_db=float(
                profile["declared_passive_loss_db"]
            ),
        )
        self.assertIn("--passiveModel=declared_scalar", command[2])
        self.assertIn("--declaredPassiveLossDb=6.5", command[2])

    def test_paper_command_carries_reproducibility_parameters(self):
        command = build_simulation_command(
            "./ns3", "hsr_velocity_connect", "repeater", 300.0, 1500.0, 10, 3, 9,
            Path("out/raw/paper"), sim_time=2.0, app_start=0.2,
            app_pkt_size=1024, saturating_load=False,
            per_ue_offered_mbps=8.19, paper_profile=True, numerology=1,
        )
        self.assertIn("--appPktSize=1024", command[2])
        self.assertIn("--saturatingLoad=0", command[2])
        self.assertIn("--numerology=1", command[2])
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

    def test_small_sample_ci_uses_student_t(self):
        self.assertAlmostEqual(t_critical_95(2), 4.303)

    def test_paper_checkpoint_rejects_failed_scenario(self):
        rows = [
            ("metal", "failed", "scheduler assertion", "1", "30", "", "", "", ""),
            ("composite", "ok", "", "1", "30", "1.0", "0.5", "2.0", "3.0"),
            ("repeater", "ok", "", "1", "30", "8.0", "0.9", "2.0", "3.0"),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "campaign_runs.csv"
            ledger.write_text(
                "scenario,status,error,numerology,scs_khz,throughput_mbps,pdr,mean_lat_ms,p95_lat_ms\n"
                + "".join(",".join(row) + "\n" for row in rows),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "metal checkpoint failed"):
                validate_checkpoint(ledger)

    def test_paper_checkpoint_accepts_consistent_zero_reception_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "campaign_runs.csv"
            ledger.write_text(
                "scenario,status,error,numerology,scs_khz,throughput_mbps,pdr,mean_lat_ms,p95_lat_ms\n"
                "metal,ok,,1,30,0.0,0.0,nan,nan\n"
                "composite,ok,,1,30,2.0,0.5,3.0,4.0\n"
                "repeater,ok,,1,30,8.0,0.9,2.0,3.0\n",
                encoding="utf-8",
            )
            results = validate_checkpoint(ledger)
        self.assertEqual(set(results), {"metal", "composite", "repeater"})
        self.assertIsNone(results["metal"]["mean_lat_ms"])
        self.assertEqual(results["repeater"]["throughput_mbps"], 8.0)

    def test_paper_checkpoint_rejects_wrong_numerology(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "campaign_runs.csv"
            ledger.write_text(
                "scenario,status,error,numerology,scs_khz,throughput_mbps,pdr,mean_lat_ms,p95_lat_ms\n"
                "metal,ok,,0,15,0.0,0.0,nan,nan\n"
                "composite,ok,,1,30,2.0,0.5,3.0,4.0\n"
                "repeater,ok,,1,30,8.0,0.9,2.0,3.0\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "metal used numerology 0"):
                validate_checkpoint(ledger)

    def test_paper_checkpoint_rejects_mislabeled_scs(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "campaign_runs.csv"
            ledger.write_text(
                "scenario,status,error,numerology,scs_khz,throughput_mbps,pdr,mean_lat_ms,p95_lat_ms\n"
                "metal,ok,,1,15,0.0,0.0,nan,nan\n"
                "composite,ok,,1,30,2.0,0.5,3.0,4.0\n"
                "repeater,ok,,1,30,8.0,0.9,2.0,3.0\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "metal used numerology 1 / 15 kHz"):
                validate_checkpoint(ledger)

    def test_paper_checkpoint_rejects_fractional_numerology(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "campaign_runs.csv"
            ledger.write_text(
                "scenario,status,error,numerology,scs_khz,throughput_mbps,pdr,mean_lat_ms,p95_lat_ms\n"
                "metal,ok,,1.5,30,0.0,0.0,nan,nan\n"
                "composite,ok,,1,30,2.0,0.5,3.0,4.0\n"
                "repeater,ok,,1,30,8.0,0.9,2.0,3.0\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "metal has non-integer numerology 1.5"):
                validate_checkpoint(ledger)


if __name__ == "__main__":
    unittest.main()
