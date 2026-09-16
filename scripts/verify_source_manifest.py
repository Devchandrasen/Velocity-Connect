from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "reproducibility" / "source_manifest.json"

REQUIRED_FILES = (
    ".gitattributes",
    ".gitignore",
    ".github/ISSUE_TEMPLATE/bug_report.yml",
    ".github/ISSUE_TEMPLATE/config.yml",
    ".github/ISSUE_TEMPLATE/reproducibility.yml",
    ".github/PULL_REQUEST_TEMPLATE.md",
    ".github/workflows/implementation-ci.yml",
    "CONTRIBUTING.md",
    "README.md",
    "REPRODUCIBILITY.md",
    "RESULTS.md",
    "EXPERIMENT_PROTOCOL.md",
    "requirements.txt",
    "pytest.ini",
    "hsr_apps.h",
    "hsr_em_channel.h",
    "hsr_handover.h",
    "hsr_io.h",
    "hsr_nr.h",
    "hsr_runner.h",
    "hsr_stats.h",
    "hsr_types.h",
    "hsr_velocity_connect.cc",
    "calibrate_passive_model.py",
    "calibration/measurement_contract.py",
    "calibration/README.md",
    "passive_feedthrough.py",
    "polarization_twisted_feedthrough.py",
    "research_campaign.py",
    "rf_feasibility.py",
    "run_corridor_campaign.py",
    "statistical_evidence.py",
    "verify_corridor_checkpoint.py",
    "measurement_template.csv",
    "docs/architecture.md",
    "docs/assets/velocity-connect-banner.svg",
    "docs/evidence-model.md",
    "docs/experiment-reference.md",
    "docs/getting-started.md",
    "docs/how-to-run-a-campaign.md",
    "environment/python-runtime.json",
    "environment/requirements-hashed-win-py312.txt",
    "environment/requirements-lock.txt",
    "environment/simulator-revisions.json",
    "environment/v3_campaign_source_provenance.json",
    "provenance/accepted_campaigns.json",
    "provenance/excluded_protocol.json",
    "provenance/excluded_protocol_transaction_v3_fqcodel_failure_20260731.json",
    "provenance/excluded_protocol_transaction_v3_interrupted_20260730.json",
    "provenance/regression_bad_ipv4_length_20260731_v3.json",
    "patches/5g-lena-v4.1.1-handover-lifetime.patch",
    "patches/5g-lena-v4.1.1-handover-wiring.patch",
    "patches/5g-lena-v4.1.1-harq-beam-order.patch",
    "patches/5g-lena-v4.1.1-harq-symbol-budget.patch",
    "patches/ns-3.48-fqcodel-short-transport-header.patch",
    "scripts/bootstrap_analysis_env.ps1",
    "scripts/analyze_vehcom_validation.py",
    "scripts/run_vehcom_validation.py",
    "scripts/run_vehcom_revision06.py",
    "scripts/start_vehcom_revision06.ps1",
    "scripts/bootstrap_ns3_v5.sh",
    "scripts/create_deterministic_zip.py",
    "scripts/generate_hashed_requirements.py",
    "scripts/run_bad_length_regression_v1.sh",
    "scripts/run_official_test_gate_v5.sh",
    "scripts/run_publication_loss_sweep_v7.sh",
    "scripts/run_transaction_campaigns_v7.sh",
    "scripts/sync_wsl_ns3_v5.sh",
    "scripts/verify_source_manifest.py",
    "hardware/analyze_vna_touchstone.py",
    "hfss/README.md",
    "hfss/requirements-hfss.txt",
    "hfss/analyze_n78_matching.py",
    "hfss/audit_radiator_power.py",
    "hfss/audit_terminal_sources.py",
    "hfss/power_balance.py",
    "hfss/export_power_budget_revision06.py",
    "hfss/replay_power_budget_revision06.py",
    "hfss/run_power_audit_guarded.ps1",
    "hfss/run_boundary_refinement_revision06.ps1",
    "hfss/build_n78_donor.py",
    "hfss/build_n78_v2_dualport.py",
    "hfss/build_n78_v2_element.py",
    "hfss/build_ptf_v4_feedthrough.py",
    "hfss/compare_n78_v2_candidates.py",
    "hfss/postprocess_n78_v2_fields.py",
    "hfss/ptf_v4_aedt_native_build.py",
    "hfss/ptf_v4_aedt_native_diagnostics.py",
    "hfss/ptf_v4_aedt_native_export_existing.py",
    "hfss/ptf_v4_aedt_native_solve_export.py",
    "hfss/ptf_v5_delay25ps_aedt_native_build.py",
    "hfss/ptf_v5_delay25ps_aedt_native_solve_export.py",
    "hfss/solve_n78_donor.py",
    "hfss/summarize_n78_v2_field_convergence.py",
    "hfss/summarize_n78_v2_tolerance.py",
    "hfss/summarize_n78_v3_installed.py",
    "hfss/tune_n78_donor.py",
    "hfss/tune_n78_feed_position.py",
    "hfss/tune_n78_flare.py",
    "hfss/Velocity_Connect_n78_V2_DualPort_S150_PowerQA_B25_B1.aedt",
    "hfss/Velocity_Connect_n78_V3_SplitRadomeFlat_E18_T1_G15_S160_PML_B30_B1.aedt",
    "hfss/Velocity_Connect_n78_V4_PTF_DualSlant_A45_H24_W16_B22_N4_G08_S160_E18_T1_G15_PML_B30_B1.aedt",
    "hfss/Velocity_Connect_PTF_V4_FourPort_Feedthrough.aedt",
    "hfss/Velocity_Connect_PTF_V5_FourPort_Delay25ps.aedt",
    "hfss/Velocity_Connect_n78_V4_PTF_DualSlant_A45_H24_W16_B22_N4_G08_S160_E18_T1_G15_PML_B25_R12_B1.aedt",
    "hfss/Velocity_Connect_Vehcom_R05_PowerClosure_B1_Radiation.aedt",
    "reproducibility/em_bridge_v1_audit.md",
    "reproducibility/vehcom_campaign_protocol.md",
    "reproducibility/radiator_power_revision05.md",
    "reproducibility/revision06_power_plan.md",
    "reproducibility/REVISION06_STATUS.md",
    "reproducibility/vehcom_revision06_execution.md",
    "fixtures/hfss/README.md",
    "fixtures/hfss/PTF_V4_Balanced_Cross.s4p",
    "fixtures/hfss/PTF_V5_Delay25ps_Cross.s4p",
    "fixtures/hfss/power_budget_revision06/README.md",
    "fixtures/hfss/power_budget_revision06/Port1_T1_boundary_flux.fld",
    "fixtures/hfss/power_budget_revision06/Port1_T1_complex_fields.csv",
    "fixtures/hfss/power_budget_revision06/Port1_T1_native.json",
    "fixtures/hfss/power_budget_revision06/Port1_T1_power_terms.json",
    "fixtures/hfss/power_budget_revision06/Port2_T1_boundary_flux.fld",
    "fixtures/hfss/power_budget_revision06/Port2_T1_complex_fields.csv",
    "fixtures/hfss/power_budget_revision06/Port2_T1_native.json",
    "fixtures/hfss/power_budget_revision06/Port2_T1_power_terms.json",
    "fixtures/hfss/power_budget_revision06/power_budget_report.json",
    "fixtures/hfss/power_budget_revision06/resource_guard.json",
    "prototype/README.md",
    "prototype/dashboard.html",
    "prototype/demo_stream.py",
    "prototype/velocity_connect/__init__.py",
    "prototype/velocity_connect/model.py",
    "prototype/velocity_connect/server.py",
    "tests/test_corridor_checkpoint.py",
    "tests/test_em_channel.cc",
    "tests/test_em_channel.py",
    "tests/test_em_channel_ns3.cc",
    "tests/test_radiator_power_audit.py",
    "tests/test_power_balance.py",
    "tests/test_repository_docs.py",
    "tests/test_calibration_contract.py",
    "tests/test_vehcom_revision06.py",
    "tests/test_vehcom_validation.py",
    "tests/test_hfss_fixtures.py",
    "tests/test_passive_feedthrough.py",
    "tests/test_polarization_twisted_feedthrough.py",
    "tests/test_prototype.py",
    "tests/test_research_campaign.py",
    "tests/test_rf_feasibility.py",
    "tests/test_statistical_evidence.py",
    "tests/test_vna_touchstone.py",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def current_manifest() -> dict[str, object]:
    missing = [name for name in REQUIRED_FILES if not (ROOT / name).is_file()]
    if missing:
        raise SystemExit("Missing required implementation files: " + ", ".join(missing))
    return {
        "schema_version": 1,
        "scope": "implementation source and compact validation fixtures only",
        "files": [
            {
                "path": name,
                "bytes": (ROOT / name).stat().st_size,
                "sha256": sha256(ROOT / name),
            }
            for name in sorted(REQUIRED_FILES)
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--write",
        action="store_true",
        help="deliberately replace the reviewed source manifest",
    )
    args = parser.parse_args()
    current = current_manifest()
    if args.write:
        MANIFEST.parent.mkdir(parents=True, exist_ok=True)
        with MANIFEST.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(current, indent=2, sort_keys=True) + "\n")
        print(f"WROTE {MANIFEST.relative_to(ROOT)} ({len(current['files'])} files)")
        return 0
    if not MANIFEST.is_file():
        raise SystemExit("Source manifest is missing; run with --write after review")
    expected = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if expected != current:
        expected_rows = {row["path"]: row for row in expected.get("files", [])}
        current_rows = {row["path"]: row for row in current["files"]}
        changed = sorted(
            name
            for name in set(expected_rows) | set(current_rows)
            if expected_rows.get(name) != current_rows.get(name)
        )
        raise SystemExit("Source manifest mismatch: " + ", ".join(changed))
    print(f"PASS source manifest ({len(current['files'])} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
