"""Contract mechanics only: ALL generated data/evidence here is synthetic.

Some tests deliberately declare measured provenance to demonstrate that a label
and matching hashes STILL never grant calibration or authenticated provenance.
Run: python -B -m unittest discover -s tests -p test_calibration_contract.py -v
"""

import contextlib
import copy
import csv
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from calibration import measurement_contract as contract


class CalibrationContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="velocity-admission-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.manifest_path = self.root / "manifest.json"
        self.rows = []
        for route, offset in (("route-a", 0), ("route-b", 1000)):
            for index in range(2):
                row = dict.fromkeys(contract.BASE_COLUMNS, 0)
                row.update(sample_id=f"{route}-{index}", route_id=route, run_id=f"{route}-run",
                           raw_file_id="raw", raw_record_id=f"record-{route}-{index}",
                           time_s=float(index), frequency_hz=3.5e9, bandwidth_hz=1e6,
                           gnb_z_m=10.0, ue_x_m=float(offset + 80 * index),
                           ue_z_m=1.5, speed_mps=80.0, power_gain_db=-90.0)
                self.rows.append(row)
        evidence = {role: self.artifact(f"{role}.txt", f"SYNTHETIC TEST ONLY: {role}\n")
                    for role in contract.EVIDENCE_ROLES}
        self.manifest = {
            "schema": contract.SCHEMA, "dataset_id": "synthetic-test-declares-measured",
            "quantity": "power_gain", "normalization": contract.NORMALIZATION,
            "units": dict(contract.UNITS), "support_policy": "exact_samples_only",
            "source": {"kind": "measured", "citation": "TEST ONLY; not field evidence",
                       "license_id": "TEST-ONLY", "evidence": evidence,
                       "raw_files": {"raw": self.artifact("raw.txt", "SYNTHETIC RAW TEST\n")}},
            "references": {key: f"TEST-ONLY {key}" for key in contract.REFERENCE_KEYS},
            "uncertainty": {"power_db": 1.0, "position_m": 0.1, "time_s": 0.001,
                            "frequency_hz": 1.0, "orientation_deg": 1.0},
            "routes": {"route-a": "physical-a", "route-b": "physical-b"},
            "split": {
                "calibration": {"route_ids": ["route-a"], "sample_ids": ["route-a-0", "route-a-1"]},
                "holdout": {"route_ids": ["route-b"], "sample_ids": ["route-b-0", "route-b-1"]},
            },
        }
        self.manifest["references"].update(time_origin_utc="2026-09-07T00:00:00Z",
                                            phase_reference="not_observed")
        self.save()

    def artifact(self, name, text):
        data = text.encode("utf-8")
        (self.root / name).write_bytes(data)
        return {"path": name, "sha256": hashlib.sha256(data).hexdigest()}

    def save_manifest(self):
        self.manifest_path.write_text(json.dumps(self.manifest), encoding="utf-8")

    def save(self):
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=contract.csv_columns(self.manifest["quantity"]))
        writer.writeheader()
        writer.writerows(self.rows)
        self.manifest["samples"] = self.artifact("samples.csv", stream.getvalue())
        self.save_manifest()

    def rejected(self, message=None):
        with self.assertRaisesRegex(contract.ContractError, message or ".+"):
            contract.admit(self.manifest_path)

    def test_complete_records_are_review_only_even_with_measured_label_and_hashes(self):
        result = contract.admit(self.manifest_path)
        report = result.report()
        self.assertEqual(report["status"], "admitted_for_review")
        self.assertFalse(result.calibration_granted)
        self.assertFalse(report["source_authenticity_verified"])
        self.assertFalse(report["bridge_export_authorized"])
        self.assertEqual(len(result.partition("calibration")), 2)
        self.assertEqual(len(result.partition("holdout")), 2)
        self.assertEqual(report["split"], self.manifest["split"])
        self.assertEqual(report["manifest_sha256"], hashlib.sha256(self.manifest_path.read_bytes()).hexdigest())

    def test_synthetic_cannot_enter_calibration_but_can_test_plumbing(self):
        self.manifest["source"]["kind"] = "synthetic"
        self.save_manifest()
        self.rejected("synthetic data")
        result = contract.admit(self.manifest_path, purpose="plumbing")
        self.assertEqual(result.source_kind, "synthetic")
        self.assertFalse(result.calibration_granted)

    def test_calibrated_labels_and_unknown_keys_are_rejected(self):
        original = copy.deepcopy(self.manifest)
        for label in ("calibrated", "measured_calibrated", "rma", "external_unvalidated"):
            with self.subTest(label=label):
                self.manifest = copy.deepcopy(original)
                self.manifest["source"]["kind"] = label
                self.save_manifest()
                self.rejected("source.kind")
        self.manifest = original
        self.manifest["calibration_granted"] = True
        self.save_manifest()
        self.rejected("require exactly")

    def test_same_route_cannot_be_randomly_row_split(self):
        self.manifest["split"]["holdout"]["route_ids"] = ["route-a"]
        self.save_manifest()
        self.rejected("whole-route")

    def test_physical_route_aliases_cannot_evade_holdout(self):
        self.manifest["routes"]["route-b"] = "physical-a"
        self.save_manifest()
        self.rejected("physical route overlap")

    def test_exact_exhaustive_split_no_unassigned_unknown_or_duplicate_samples(self):
        original = copy.deepcopy(self.manifest)
        for ids in (["route-a-0"], ["route-a-0", "route-a-1", "invented"],
                    ["route-a-0", "route-a-0"], []):
            with self.subTest(ids=ids):
                self.manifest = copy.deepcopy(original)
                self.manifest["split"]["calibration"]["sample_ids"] = ids
                self.save_manifest()
                self.rejected()

    def test_no_unassigned_routes(self):
        self.manifest["split"]["holdout"] = copy.deepcopy(self.manifest["split"]["calibration"])
        self.save_manifest()
        self.rejected("overlap")

    def test_missing_uncertainty_and_invalid_numbers_fail_closed(self):
        original = copy.deepcopy(self.manifest)
        for value in (0, -1, float("nan"), float("inf"), True, "0.1", None, 10 ** 400):
            with self.subTest(value=str(value)[:40]):
                self.manifest = copy.deepcopy(original)
                self.manifest["uncertainty"]["time_s"] = value
                self.save_manifest()
                self.rejected()
        self.manifest = original
        del self.manifest["uncertainty"]["power_db"]
        self.save_manifest()
        self.rejected("require exactly")

    def test_nonfinite_missing_and_nonpositive_csv_metadata(self):
        original = copy.deepcopy(self.rows)
        cases = [(column, value) for column in ("frequency_hz", "ue_x_m", "time_s", "power_gain_db")
                 for value in ("", "NA", "NaN", "inf", "-inf", "1e999")]
        cases += [("frequency_hz", 0), ("frequency_hz", -1), ("frequency_hz", 6e9),
                  ("bandwidth_hz", 0), ("bandwidth_hz", -1), ("bandwidth_hz", 8e9),
                  ("speed_mps", -1), ("time_s", -1), ("power_gain_db", 1),
                  ("tx_pitch_deg", 91)]
        for column, value in cases:
            with self.subTest(column=column, value=value):
                self.rows = copy.deepcopy(original)
                self.rows[0][column] = value
                self.save()
                self.rejected()

    def test_negative_coordinates_and_db_are_valid_not_missing(self):
        self.rows[0]["ue_x_m"] = -50
        self.rows[0]["power_gain_db"] = -100
        self.save()
        self.assertEqual(contract.admit(self.manifest_path).rows[0]["ue_x_m"], -50)

    def test_no_values_or_rows_are_filled_or_rewritten(self):
        self.rows[0]["ue_x_m"] = ""
        self.save()
        before = {p.name: p.read_bytes() for p in self.root.iterdir()}
        self.rejected()
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.root.iterdir()})

    def test_empty_legacy_scalar_template_is_not_admissible(self):
        self.manifest["samples"] = self.artifact("samples.csv", "sample_id,frequency_hz,feeder_s21_db\n")
        self.save_manifest()
        self.rejected("header")

    def test_bad_csv_structure_rejected(self):
        original = (self.root / "samples.csv").read_text(encoding="utf-8")
        for text in (original + "\n", original + "bad,row\n", original.splitlines()[0] + "\n",
                     original.replace("sample_id,", "sample_id,sample_id,", 1)):
            with self.subTest(text=text[-30:]):
                self.manifest["samples"] = self.artifact("samples.csv", text)
                self.save_manifest()
                self.rejected()

    def test_duplicate_sample_and_raw_observation_rejected(self):
        original = copy.deepcopy(self.rows)
        for field in ("sample_id", "raw_record_id"):
            with self.subTest(field=field):
                self.rows = copy.deepcopy(original)
                self.rows[2][field] = self.rows[0][field]
                self.save()
                self.rejected("duplicate sample|reused raw")

    def test_run_alias_leakage_rejected(self):
        for row in self.rows[2:]:
            row["run_id"] = self.rows[0]["run_id"]
        self.save()
        self.rejected("run_id reused")

    def test_hash_mismatch_and_empty_or_absent_evidence_rejected(self):
        (self.root / "acquisition.txt").write_text("changed", encoding="utf-8")
        self.rejected("sha256 mismatch")
        self.manifest["source"]["evidence"]["acquisition"] = self.artifact("acquisition.txt", "")
        self.save_manifest()
        self.rejected("empty file")
        (self.root / "acquisition.txt").unlink()
        self.rejected("missing/unsafe file")

    def test_unknown_raw_file_and_duplicate_raw_content(self):
        self.rows[0]["raw_file_id"] = "absent"
        self.save()
        self.rejected("raw file IDs")
        self.manifest["source"]["raw_files"]["alias"] = copy.deepcopy(
            self.manifest["source"]["raw_files"]["raw"])
        self.save_manifest()
        self.rejected("duplicate raw bytes")

    def test_path_escape_and_invalid_hash(self):
        ref = self.manifest["source"]["evidence"]["license"]
        for value in ("../outside", "/etc/passwd", "C:/outside", "C:outside", "a\\b"):
            with self.subTest(path=value):
                ref["path"] = value
                self.save_manifest()
                self.rejected("unsafe relative path")
        ref["path"] = "license.txt"
        ref["sha256"] = "claimed-measured"
        self.save_manifest()
        self.rejected("sha256")

    def test_symlink_escape(self):
        with tempfile.TemporaryDirectory(prefix="velocity-admission-outside-") as outside:
            target = Path(outside) / "outside.txt"
            target.write_text("test", encoding="utf-8")
            link = self.root / "link.txt"
            try:
                link.symlink_to(target)
            except OSError:
                self.skipTest("host does not allow creation of test symlinks")
            self.manifest["source"]["evidence"]["license"] = {
                "path": "link.txt", "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}
            self.save_manifest()
            self.rejected("missing/unsafe file")

    def test_units_references_time_and_phase_are_not_guessed(self):
        original = copy.deepcopy(self.manifest)
        for key, value in (("time_origin_utc", "2026-09-07T00:00:00"),
                           ("time_origin_utc", "2026-99-99T00:00:00Z"),
                           ("basis", "unknown"), ("tx_reference_plane", ""),
                           ("phase_reference", "assumed_zero")):
            with self.subTest(key=key, value=value):
                self.manifest = copy.deepcopy(original)
                self.manifest["references"][key] = value
                self.save_manifest()
                self.rejected()
        self.manifest = original
        self.manifest["units"]["frequency"] = "GHz"
        self.save_manifest()
        self.rejected("units")

    def test_duplicate_json_keys_rejected(self):
        content = self.manifest_path.read_text(encoding="utf-8")
        self.manifest_path.write_text('{"schema":"calibrated",' + content[1:], encoding="utf-8")
        self.rejected("duplicate key")

    def test_missing_and_malformed_manifest_cli(self):
        for content in ("[]", "null", "{invalid", ""):
            with self.subTest(content=content):
                self.manifest_path.write_text(content, encoding="utf-8")
                stream = io.StringIO()
                with contextlib.redirect_stdout(stream):
                    code = contract.main([str(self.manifest_path)])
                self.assertEqual(code, 2)
                self.assertFalse(json.loads(stream.getvalue())["calibration_granted"])

    def test_cli_success_means_review_not_calibration(self):
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            self.assertEqual(contract.main([str(self.manifest_path)]), 0)
        self.assertFalse(json.loads(stream.getvalue())["calibration_granted"])

    def test_absent_manifest_and_bounded_input_sizes(self):
        with self.assertRaises(contract.ContractError):
            contract.admit(self.root / "absent.json")
        with patch.object(contract, "MAX_MANIFEST_BYTES", 10):
            self.rejected("manifest exceeds")
        with patch.object(contract, "MAX_SAMPLES_BYTES", 10):
            self.rejected("file exceeds")

    def test_every_evidence_role_is_mandatory(self):
        original = copy.deepcopy(self.manifest)
        for role in contract.EVIDENCE_ROLES:
            with self.subTest(role=role):
                self.manifest = copy.deepcopy(original)
                del self.manifest["source"]["evidence"][role]
                self.save_manifest()
                self.rejected("require exactly")

    def test_exact_support_and_holdout_isolation(self):
        admitted = contract.admit(self.manifest_path)
        row = admitted.rows[0]
        context = {c: row[c] for c in contract.CONTEXT_COLUMNS}
        self.assertEqual(admitted.require_support(row["sample_id"], partition="calibration", context=context), row)
        with self.assertRaisesRegex(contract.ContractError, "partition"):
            admitted.require_support(row["sample_id"], partition="holdout", context=context)
        for field, value in (("time_s", 0.5), ("frequency_hz", 3.5001e9),
                             ("ue_x_m", 1), ("tx_yaw_deg", 1), ("speed_mps", 81),
                             ("route_id", "unknown-route"), ("bandwidth_hz", 2e6)):
            with self.subTest(field=field):
                changed = dict(context, **{field: value})
                with self.assertRaisesRegex(contract.ContractError, "forbidden"):
                    admitted.require_support(row["sample_id"], partition="calibration", context=changed)
        del context["time_s"]
        with self.assertRaisesRegex(contract.ContractError, "require exactly"):
            admitted.require_support(row["sample_id"], partition="calibration", context=context)

    def test_snapshot_is_immutable_and_new_bytes_require_new_admission(self):
        admitted = contract.admit(self.manifest_path)
        with self.assertRaises(TypeError):
            admitted.rows[0]["power_gain_db"] = -1
        with self.assertRaises(TypeError):
            admitted.splits["holdout"] = ()
        (self.root / "samples.csv").write_text("changed", encoding="utf-8")
        self.assertEqual(admitted.rows[0]["power_gain_db"], -90)
        self.rejected("sha256 mismatch")

    def test_static_records_and_policy_broadening_rejected(self):
        self.rows[1]["ue_x_m"] = self.rows[0]["ue_x_m"]
        self.save()
        self.rejected("moving UE")
        self.manifest["support_policy"] = "linear_interpolation"
        self.save_manifest()
        self.rejected("forbidden")

    def make_operators(self):
        self.manifest["quantity"] = "em_operators"
        self.manifest["uncertainty"]["phase_deg"] = 1.0
        self.manifest["references"]["phase_reference"] = "SYNTHETIC TEST shared phase reference"
        for row in self.rows:
            del row["power_gain_db"]
            row.update(dict.fromkeys(contract.OPERATOR_COLUMNS + contract.PROJECTION_COLUMNS, 0.0))
            row.update(tx0_re=1.0, rx0_re=1.0, d00_re=0.01, d11_re=0.01,
                       in00_re=0.1, in11_re=0.1, out00_re=0.1, out11_re=0.1)
        self.save()

    def test_complex_operator_header_alignment_and_no_phase_synthesis(self):
        self.make_operators()
        admitted = contract.admit(self.manifest_path)
        self.assertEqual(admitted.quantity, "em_operators")
        self.assertEqual(contract.OPERATOR_COLUMNS[:4], ("d00_re", "d00_im", "d01_re", "d01_im"))
        self.assertEqual(contract.OPERATOR_COLUMNS[-2:], ("out11_re", "out11_im"))
        self.assertEqual(len(contract.OPERATOR_COLUMNS), 24)
        self.manifest["references"]["phase_reference"] = "not_observed"
        self.save_manifest()
        self.rejected("coherent phase")

    def test_operators_must_be_contractions_not_just_bounded_entries(self):
        self.make_operators()
        self.rows[0].update(d00_re=0.8, d01_re=0.8, d10_re=0.0, d11_re=0.0)
        self.save()
        self.rejected("passive power bound")

    def test_complex_queries_require_exact_projections_and_phase_uncertainty(self):
        self.make_operators()
        admitted = contract.admit(self.manifest_path)
        row = admitted.rows[0]
        context = {c: row[c] for c in contract.CONTEXT_COLUMNS + contract.PROJECTION_COLUMNS}
        self.assertEqual(admitted.require_support(row["sample_id"], partition="calibration", context=context), row)
        context["tx0_re"] = 0.5
        with self.assertRaisesRegex(contract.ContractError, "forbidden"):
            admitted.require_support(row["sample_id"], partition="calibration", context=context)
        del self.manifest["uncertainty"]["phase_deg"]
        self.save_manifest()
        self.rejected("require exactly")

    def test_operator_missing_zero_and_bad_projection_are_not_repaired(self):
        self.make_operators()
        self.rows[0]["d01_im"] = ""
        self.save()
        self.rejected("invalid number")
        self.rows[0]["d01_im"] = 0
        self.rows[0]["tx0_re"] = 2
        self.save()
        self.rejected("unit power norm")

    def test_same_time_different_frequency_cannot_change_geometry(self):
        extra = dict(self.rows[0], sample_id="extra", raw_record_id="extra",
                     frequency_hz=3.51e9, ue_x_m=999)
        self.rows.append(extra)
        self.manifest["split"]["calibration"]["sample_ids"].append("extra")
        self.save()
        self.rejected("inconsistent geometry")


if __name__ == "__main__":
    unittest.main()
