"""Offline, fail-closed moving-link record admission; never calibration certification.

Only Python's standard library is used. No interpolation, model fitting, operator
synthesis, simulator invocation, network access, or file writes are performed.
See README.md for the schema, trust boundary, and evidence still required.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PureWindowsPath
import re
from types import MappingProxyType
from typing import Mapping


SCHEMA = "hsr-moving-link-admission-v1"
NORMALIZATION = "absolute_power_waves_50ohm"
UNITS = {"frequency": "Hz", "bandwidth": "Hz", "time": "s", "position": "m",
         "speed": "m/s", "orientation": "deg", "power_gain": "dB", "operator": "1"}
IDENTIFIERS = ("sample_id", "route_id", "run_id", "raw_file_id", "raw_record_id")
POSITION_COLUMNS = tuple(f"{end}_{axis}_m" for end in ("gnb", "ue") for axis in "xyz")
ANGLE_COLUMNS = tuple(f"{end}_{axis}_deg" for end in ("tx", "rx")
                      for axis in ("yaw", "pitch", "roll"))
CONTEXT_COLUMNS = ("route_id", "run_id", "time_s", "frequency_hz", "bandwidth_hz",
                   *POSITION_COLUMNS, "speed_mps", *ANGLE_COLUMNS)
BASE_COLUMNS = (*IDENTIFIERS, *CONTEXT_COLUMNS[2:])
# Exact names/order from hsr::em::OperatorHeader(), excluding frequency_hz.
OPERATOR_COLUMNS = tuple(f"{name}{ij}_{part}" for name in ("d", "in", "out")
                         for ij in ("00", "01", "10", "11") for part in ("re", "im"))
PROJECTION_COLUMNS = tuple(f"{end}{i}_{part}" for end in ("tx", "rx")
                           for i in (0, 1) for part in ("re", "im"))
PARTITIONS = ("calibration", "holdout")
EVIDENCE_ROLES = ("license", "acquisition", "instrument_calibration", "processing",
                  "antenna_reference", "route_identity", "uncertainty", "split_plan")
REFERENCE_KEYS = ("coordinate_frame", "time_origin_utc", "clock_reference", "basis",
                  "phase_reference", "tx_antenna", "rx_antenna", "tx_reference_plane",
                  "rx_reference_plane", "orientation_convention")
PLACEHOLDERS = {"", "unknown", "none", "null", "nan", "na", "n/a", "tbd", "todo"}
MAX_MANIFEST_BYTES = 4 * 1024 * 1024
MAX_SAMPLES_BYTES = 64 * 1024 * 1024


class ContractError(ValueError):
    """A package is inadmissible; no fields have been repaired or filled."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def _keys(value: object, expected, where: str) -> dict:
    _require(isinstance(value, dict), f"{where}: expected object")
    _require(set(value) == set(expected), f"{where}: require exactly {sorted(expected)}")
    return value


def _text(value: object, where: str) -> str:
    _require(isinstance(value, str) and value == value.strip()
             and value.casefold() not in PLACEHOLDERS, f"{where}: missing/placeholder text")
    _require(not any(ord(c) < 32 for c in value), f"{where}: control character")
    return value


def _number(value: object, where: str, *, csv_cell: bool = False) -> float:
    _require(type(value) in ((str,) if csv_cell else (int, float)),
             f"{where}: expected numeric {'CSV cell' if csv_cell else 'JSON value'}")
    try:
        result = float(value)
    except (ValueError, OverflowError) as exc:
        raise ContractError(f"{where}: invalid number") from exc
    _require(math.isfinite(result), f"{where}: must be finite")
    return result


def _unique_list(value: object, where: str) -> tuple[str, ...]:
    _require(isinstance(value, list) and bool(value), f"{where}: nonempty list required")
    result = tuple(_text(x, where) for x in value)
    _require(len(set(result)) == len(result), f"{where}: duplicate entry")
    return result


def _json_object(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, f"JSON: duplicate key {key}")
        result[key] = value
    return result


def _bad_constant(value):
    raise ContractError(f"JSON: non-finite constant {value}")


def csv_columns(quantity: str) -> tuple[str, ...]:
    """Return the exact required CSV header; no nullable or optional columns."""
    _require(quantity in ("power_gain", "em_operators"), "unsupported quantity")
    return (*BASE_COLUMNS, "power_gain_db") if quantity == "power_gain" else (
        *BASE_COLUMNS, *PROJECTION_COLUMNS, *OPERATOR_COLUMNS)


def _artifact(root: Path, reference: object, where: str, *, capture_limit=None):
    ref = _keys(reference, ("path", "sha256"), where)
    relative = _text(ref["path"], f"{where}.path")
    # A portable bundle uses forward-slash relative paths. Check Windows drives
    # even on POSIX; resolve symlinks/junctions before enforcing the bundle root.
    _require("\\" not in relative and ":" not in relative
             and not Path(relative).is_absolute()
             and not PureWindowsPath(relative).drive and not PureWindowsPath(relative).root
             and ".." not in Path(relative).parts, f"{where}: unsafe relative path")
    path = (root / relative).resolve()
    _require(path.is_relative_to(root) and path.is_file(), f"{where}: missing/unsafe file")
    digest = _text(ref["sha256"], f"{where}.sha256")
    _require(re.fullmatch(r"[0-9a-f]{64}", digest) is not None, f"{where}: invalid sha256")
    hasher, chunks, size = hashlib.sha256(), [], 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            size += len(chunk)
            if capture_limit is not None:
                _require(size <= capture_limit, f"{where}: file exceeds size limit")
                chunks.append(chunk)
            hasher.update(chunk)
    _require(size > 0, f"{where}: empty file")
    _require(hasher.hexdigest() == digest, f"{where}: sha256 mismatch")
    # Hashes establish byte identity, NOT the truth or authority of a document.
    return digest, b"".join(chunks)


def _check_matrix(row: Mapping, name: str) -> None:
    h = [complex(row[f"{name}{ij}_re"], row[f"{name}{ij}_im"])
         for ij in ("00", "01", "10", "11")]
    _require(all(abs(x) <= 1 + 1e-8 for x in h), f"{name}: passive power bound")
    a, d = abs(h[0]) ** 2 + abs(h[2]) ** 2, abs(h[1]) ** 2 + abs(h[3]) ** 2
    b = h[0].conjugate() * h[1] + h[2].conjugate() * h[3]
    gain = (a + d + math.hypot(a - d, 2 * abs(b))) / 2
    _require(math.isfinite(gain) and gain <= 1 + 1e-8, f"{name}: passive power bound")


def _read_rows(data: bytes, quantity: str) -> tuple[Mapping, ...]:
    reader = csv.reader(io.StringIO(data.decode("utf-8-sig"), newline=""), strict=True)
    columns = csv_columns(quantity)
    _require(next(reader, None) == list(columns), "CSV: unexpected header/order")
    records = []
    ids, raw_keys, observations = set(), set(), set()
    for cells in reader:
        where = f"CSV line {reader.line_num}"
        _require(len(cells) == len(columns), f"{where}: incomplete/extra/blank row")
        row = dict(zip(columns, cells))
        for column in IDENTIFIERS:
            row[column] = _text(row[column], f"{where}.{column}")
        for column in columns[len(IDENTIFIERS):]:
            row[column] = _number(row[column], f"{where}.{column}", csv_cell=True)
        _require(row["sample_id"] not in ids, f"{where}: duplicate sample_id")
        ids.add(row["sample_id"])
        raw_key = (row["raw_file_id"], row["raw_record_id"])
        _require(raw_key not in raw_keys, f"{where}: reused raw observation")
        raw_keys.add(raw_key)
        observation = tuple(row[k] for k in ("route_id", "run_id", "time_s", "frequency_hz"))
        _require(observation not in observations, f"{where}: duplicate observation")
        observations.add(observation)
        _require(row["time_s"] >= 0 and row["speed_mps"] >= 0,
                 f"{where}: negative time/speed")
        f, bw = row["frequency_hz"], row["bandwidth_hz"]
        _require(bw > 0 and 0 < f - bw / 2 <= f + bw / 2 < 6e9,
                 f"{where}: positive sub-6 frequency/bandwidth support required")
        for column in ANGLE_COLUMNS:
            limit = 90 if "pitch" in column else 180
            _require(-limit <= row[column] <= limit, f"{where}: invalid orientation {column}")
        if quantity == "power_gain":
            _require(row["power_gain_db"] <= 0, f"{where}: passive power gain exceeds 0 dB")
        else:
            for end in ("tx", "rx"):
                values = [row[c] for c in PROJECTION_COLUMNS if c.startswith(end)]
                _require(all(abs(x) <= 1 for x in values)
                         and abs(sum(x*x for x in values) - 1) < 1e-9,
                         f"{where}: {end} projection must have unit power norm")
            for name in ("d", "in", "out"):
                _check_matrix(row, name)
        records.append(MappingProxyType(row))
    _require(bool(records), "CSV: no observations")
    return tuple(records)


@dataclass(frozen=True)
class Admission:
    """Immutable admission snapshot. This is not an authenticated certificate."""

    dataset_id: str
    source_kind: str
    purpose: str
    quantity: str
    manifest_sha256: str
    artifact_sha256: Mapping[str, str]
    rows: tuple[Mapping, ...]
    splits: Mapping[str, tuple[str, ...]]
    routes: Mapping[str, tuple[str, ...]]

    @property
    def calibration_granted(self) -> bool:
        return False

    def report(self) -> dict:
        return {
            "schema": SCHEMA, "status": "admitted_for_review", "purpose": self.purpose,
            "dataset_id": self.dataset_id, "declared_source_kind": self.source_kind,
            "quantity": self.quantity, "calibration_granted": False,
            "bridge_export_authorized": False, "source_authenticity_verified": False,
            "manifest_sha256": self.manifest_sha256,
            "artifact_sha256": dict(self.artifact_sha256),
            "split": {p: {"route_ids": list(self.routes[p]), "sample_ids": list(self.splits[p])}
                      for p in PARTITIONS},
            "support_policy": "exact_samples_only",
            "limitations": ["Integrity and completeness only; labels/hashes cannot certify measurements.",
                            "Independent acquisition, rights, reference-plane and uncertainty review required.",
                            "No model fitted, holdout score produced, or moving C++ provider implemented."],
        }

    def partition(self, name: str) -> tuple[Mapping, ...]:
        _require(name in PARTITIONS, "unknown partition")
        ids = set(self.splits[name])
        return tuple(row for row in self.rows if row["sample_id"] in ids)

    def require_support(self, sample_id: str, *, partition: str, context: dict) -> Mapping:
        """Return only an exact recorded context in the requested partition.

        No bounding-box, nearest-neighbour, clamping, tolerance, frequency-band
        fill, route transfer, interpolation or extrapolation is licensed here.
        """
        columns = CONTEXT_COLUMNS + (PROJECTION_COLUMNS if self.quantity == "em_operators" else ())
        _keys(context, columns, "query context")
        normalized = {k: (_text(context[k], k) if k in ("route_id", "run_id")
                          else _number(context[k], k)) for k in columns}
        for row in self.partition(partition):
            if row["sample_id"] == sample_id:
                _require(all(normalized[k] == row[k] for k in columns),
                         "unsupported context: interpolation/extrapolation forbidden")
                return row
        raise ContractError("sample not in requested partition; holdout leakage/unknown support")


def admit(manifest_path: str | Path, *, purpose: str = "calibration") -> Admission:
    """Validate local JSON + CSV + pinned evidence; raise ContractError on failure.

    `calibration` means admission to review for a potential calibration study,
    never approval of calibration. Synthetic packages are allowed only for
    `plumbing`. Claims of calibrated/certified evidence are unsupported.
    """
    try:
        return _admit(Path(manifest_path), purpose)
    except ContractError:
        raise
    except (OSError, ValueError, TypeError, OverflowError, RuntimeError, csv.Error) as exc:
        raise ContractError(f"unreadable or malformed package: {exc}") from exc


def _admit(manifest_path: Path, purpose: str) -> Admission:
    _require(purpose in ("calibration", "plumbing"), "purpose must be calibration or plumbing")
    with manifest_path.open("rb") as stream:
        raw_manifest = stream.read(MAX_MANIFEST_BYTES + 1)
    _require(len(raw_manifest) <= MAX_MANIFEST_BYTES, "manifest exceeds size limit")
    manifest = json.loads(raw_manifest.decode("utf-8-sig"), object_pairs_hook=_json_object,
                          parse_constant=_bad_constant)
    m = _keys(manifest, ("schema", "dataset_id", "quantity", "normalization", "units",
                         "source", "references", "uncertainty", "routes", "split",
                         "support_policy", "samples"), "manifest")
    _require(m["schema"] == SCHEMA, "unsupported schema")
    dataset_id = _text(m["dataset_id"], "dataset_id")
    csv_columns(m["quantity"])
    _require(m["normalization"] == NORMALIZATION, "explicit 50-ohm power waves required")
    _require(m["units"] == UNITS, "units must exactly match the contract; no inferred conversion")
    _require(m["support_policy"] == "exact_samples_only", "extrapolation/interpolation forbidden")
    source = _keys(m["source"], ("kind", "citation", "license_id", "raw_files", "evidence"), "source")
    _require(source["kind"] in ("measured", "synthetic"), "source.kind must be measured or synthetic")
    _require(purpose != "calibration" or source["kind"] == "measured",
             "synthetic data cannot be admitted for calibration")
    for key in ("citation", "license_id"):
        _text(source[key], f"source.{key}")
    refs = _keys(m["references"], REFERENCE_KEYS, "references")
    for key, value in refs.items():
        _text(value, f"references.{key}")
    _require(refs["time_origin_utc"].endswith("Z"), "time origin requires explicit UTC Z")
    origin = datetime.fromisoformat(refs["time_origin_utc"][:-1] + "+00:00")
    _require("T" in refs["time_origin_utc"] and origin.utcoffset().total_seconds() == 0,
             "time origin requires UTC date and time")
    if m["quantity"] == "power_gain":
        _require(refs["phase_reference"] == "not_observed",
                 "scalar power does not measure phase; use not_observed")
    else:
        _require(refs["phase_reference"] != "not_observed", "complex operators need coherent phase reference")
    uncertainty_keys = ("power_db", "position_m", "time_s", "frequency_hz", "orientation_deg")
    if m["quantity"] == "em_operators":
        uncertainty_keys += ("phase_deg",)
    uncertainty = _keys(m["uncertainty"], uncertainty_keys, "uncertainty")
    for key, value in uncertainty.items():
        _require(_number(value, f"uncertainty.{key}") > 0, f"uncertainty.{key}: must be positive")

    root = manifest_path.resolve().parent
    artifacts = {}
    evidence = _keys(source["evidence"], EVIDENCE_ROLES, "source.evidence")
    for role, ref in evidence.items():
        artifacts[f"evidence.{role}"] = _artifact(root, ref, f"evidence.{role}")[0]
    raw_files = source["raw_files"]
    _require(isinstance(raw_files, dict) and bool(raw_files), "source.raw_files: nonempty object required")
    raw_digests = set()
    for raw_id, ref in raw_files.items():
        _text(raw_id, "raw_file_id")
        digest = _artifact(root, ref, f"raw_files.{raw_id}")[0]
        _require(digest not in raw_digests, "duplicate raw bytes under different file IDs")
        raw_digests.add(digest)
        artifacts[f"raw.{raw_id}"] = digest
    artifacts["samples"], data = _artifact(root, m["samples"], "samples", capture_limit=MAX_SAMPLES_BYTES)
    rows = _read_rows(data, m["quantity"])
    _require({r["raw_file_id"] for r in rows} == set(raw_files), "CSV/raw file IDs do not match exactly")

    routes = m["routes"]
    _require(isinstance(routes, dict) and bool(routes), "routes: nonempty object required")
    for route, physical_route in routes.items():
        _text(route, "route_id")
        _text(physical_route, "physical_route_id")
    _require({r["route_id"] for r in rows} == set(routes), "CSV/route IDs do not match exactly")
    split = _keys(m["split"], PARTITIONS, "split")
    sample_splits, route_splits, physical_splits = {}, {}, {}
    for name in PARTITIONS:
        part = _keys(split[name], ("route_ids", "sample_ids"), f"split.{name}")
        route_splits[name] = _unique_list(part["route_ids"], f"split.{name}.route_ids")
        sample_splits[name] = _unique_list(part["sample_ids"], f"split.{name}.sample_ids")
        _require(set(route_splits[name]) <= set(routes), "split: unknown route")
        physical_splits[name] = {routes[r] for r in route_splits[name]}
        expected = {r["sample_id"] for r in rows if r["route_id"] in route_splits[name]}
        _require(set(sample_splits[name]) == expected, f"split.{name}: exact whole-route membership required")
    for values, description in ((sample_splits, "sample"), (route_splits, "route"),
                                (physical_splits, "physical route")):
        _require(not set(values["calibration"]) & set(values["holdout"]),
                 f"split: {description} overlap/leakage")
    _require(set(route_splits["calibration"]) | set(route_splits["holdout"]) == set(routes),
             "split: unassigned route")
    # Every run must show actual movement; static snapshots are not moving-link data.
    runs = {}
    for row in rows:
        _require(row["run_id"] not in runs or runs[row["run_id"]][0] == row["route_id"],
                 "run_id reused across routes")
        runs.setdefault(row["run_id"], (row["route_id"], []))[1].append(row)
    for run, (_, records) in runs.items():
        positions = {tuple(r[c] for c in POSITION_COLUMNS[3:]) for r in records}
        times = {r["time_s"] for r in records}
        _require(len(positions) >= 2 and len(times) >= 2 and any(r["speed_mps"] > 0 for r in records),
                 f"{run}: at least two distinct moving UE positions/times required")
        snapshots = {}
        for row in records:
            geometry = tuple(row[c] for c in (*POSITION_COLUMNS, "speed_mps", *ANGLE_COLUMNS))
            previous = snapshots.setdefault(row["time_s"], geometry)
            _require(previous == geometry, f"{run}: inconsistent geometry at one time")
    return Admission(dataset_id, source["kind"], purpose, m["quantity"],
                     hashlib.sha256(raw_manifest).hexdigest(), MappingProxyType(artifacts), rows,
                     MappingProxyType(sample_splits), MappingProxyType(route_splits))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--purpose", choices=("calibration", "plumbing"), default="calibration")
    args = parser.parse_args(argv)
    try:
        report = admit(args.manifest, purpose=args.purpose).report()
    except ContractError as exc:
        print(json.dumps({"status": "rejected", "calibration_granted": False,
                          "bridge_export_authorized": False, "error": str(exc)}, allow_nan=False))
        return 2
    print(json.dumps(report, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
