"""Telemetry validation, evidence persistence, and paired KPI reporting."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import threading
from typing import Any, Iterable, Mapping


SCHEMA_VERSION = "1.0"
ALLOWED_CONDITIONS = {"baseline", "passive"}
ALLOWED_SOURCES = {"demo", "ns3", "modem", "scanner", "srsran"}
METRICS = (
    "rsrp_dbm",
    "sinr_db",
    "dl_mbps",
    "ul_mbps",
    "latency_ms",
    "packet_loss_pct",
)


def _require_text(payload: Mapping[str, Any], field: str, *, max_length: int = 128) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    value = value.strip()
    if len(value) > max_length:
        raise ValueError(f"{field} must be at most {max_length} characters")
    if any(char in value for char in ("\r", "\n", "\x00")):
        raise ValueError(f"{field} contains a forbidden control character")
    return value


def _require_number(
    payload: Mapping[str, Any],
    field: str,
    minimum: float,
    maximum: float,
) -> float:
    value = payload.get(field)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{field} must be finite")
    if not minimum <= result <= maximum:
        raise ValueError(f"{field} must be between {minimum} and {maximum}")
    return result


def _optional_coordinate(
    payload: Mapping[str, Any], field: str, minimum: float, maximum: float
) -> float | None:
    if payload.get(field) is None:
        return None
    return _require_number(payload, field, minimum, maximum)


def _normalize_timestamp(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("timestamp_utc must be a non-empty RFC3339 string")
    text = value.strip()
    parseable = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(parseable)
    except ValueError as exc:
        raise ValueError("timestamp_utc must be valid RFC3339/ISO-8601") from exc
    if parsed.tzinfo is None:
        raise ValueError("timestamp_utc must include a timezone")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def validate_sample(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and normalize one canonical telemetry sample."""

    if not isinstance(payload, Mapping):
        raise ValueError("sample must be a JSON object")

    schema_version = _require_text(payload, "schema_version", max_length=16)
    if schema_version != SCHEMA_VERSION:
        raise ValueError(f"schema_version must be {SCHEMA_VERSION}")

    condition = _require_text(payload, "condition", max_length=16).lower()
    if condition not in ALLOWED_CONDITIONS:
        raise ValueError("condition must be baseline or passive")

    source = _require_text(payload, "source", max_length=16).lower()
    if source not in ALLOWED_SOURCES:
        raise ValueError(f"source must be one of {sorted(ALLOWED_SOURCES)}")

    sequence = payload.get("sequence")
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
        raise ValueError("sequence must be a non-negative integer")

    return {
        "schema_version": schema_version,
        "run_id": _require_text(payload, "run_id"),
        "sequence": sequence,
        "condition": condition,
        "source": source,
        "timestamp_utc": _normalize_timestamp(payload.get("timestamp_utc")),
        "segment_id": _require_text(payload, "segment_id"),
        "seat_id": _require_text(payload, "seat_id", max_length=64),
        "speed_kmph": _require_number(payload, "speed_kmph", 0.0, 650.0),
        "latitude": _optional_coordinate(payload, "latitude", -90.0, 90.0),
        "longitude": _optional_coordinate(payload, "longitude", -180.0, 180.0),
        "rsrp_dbm": _require_number(payload, "rsrp_dbm", -160.0, -20.0),
        "sinr_db": _require_number(payload, "sinr_db", -40.0, 60.0),
        "dl_mbps": _require_number(payload, "dl_mbps", 0.0, 10000.0),
        "ul_mbps": _require_number(payload, "ul_mbps", 0.0, 10000.0),
        "latency_ms": _require_number(payload, "latency_ms", 0.0, 60000.0),
        "packet_loss_pct": _require_number(payload, "packet_loss_pct", 0.0, 100.0),
    }


def _mean(values: Iterable[float]) -> float:
    materialized = list(values)
    return sum(materialized) / len(materialized) if materialized else 0.0


def _condition_summary(samples: list[dict[str, Any]]) -> dict[str, Any]:
    if not samples:
        return {"count": 0, "outage_rate_pct": 0.0, **{name: None for name in METRICS}}
    outages = sum(
        1 for sample in samples if sample["dl_mbps"] < 1.0 or sample["packet_loss_pct"] > 10.0
    )
    summary: dict[str, Any] = {
        "count": len(samples),
        "outage_rate_pct": 100.0 * outages / len(samples),
    }
    for metric in METRICS:
        summary[metric] = _mean(sample[metric] for sample in samples)
    return summary


def build_report(samples: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Build condition summaries and paired, direction-aware improvement KPIs."""

    rows = list(samples)
    by_condition = {
        condition: [row for row in rows if row["condition"] == condition]
        for condition in sorted(ALLOWED_CONDITIONS)
    }

    grouped: dict[tuple[str, str], dict[str, list[dict[str, Any]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for row in rows:
        grouped[(row["segment_id"], row["seat_id"])][row["condition"]].append(row)

    paired_deltas: list[dict[str, float]] = []
    for conditions in grouped.values():
        if not all(condition in conditions for condition in ALLOWED_CONDITIONS):
            continue
        baseline = {metric: _mean(row[metric] for row in conditions["baseline"]) for metric in METRICS}
        passive = {metric: _mean(row[metric] for row in conditions["passive"]) for metric in METRICS}
        baseline_outage = _mean(
            1.0 if row["dl_mbps"] < 1.0 or row["packet_loss_pct"] > 10.0 else 0.0
            for row in conditions["baseline"]
        )
        passive_outage = _mean(
            1.0 if row["dl_mbps"] < 1.0 or row["packet_loss_pct"] > 10.0 else 0.0
            for row in conditions["passive"]
        )
        paired_deltas.append(
            {
                "rsrp_gain_db": passive["rsrp_dbm"] - baseline["rsrp_dbm"],
                "sinr_gain_db": passive["sinr_db"] - baseline["sinr_db"],
                "dl_gain_mbps": passive["dl_mbps"] - baseline["dl_mbps"],
                "ul_gain_mbps": passive["ul_mbps"] - baseline["ul_mbps"],
                "latency_reduction_ms": baseline["latency_ms"] - passive["latency_ms"],
                "packet_loss_reduction_pct_points": (
                    baseline["packet_loss_pct"] - passive["packet_loss_pct"]
                ),
                "outage_reduction_pct_points": 100.0 * (baseline_outage - passive_outage),
            }
        )

    unpaired = len(grouped) - len(paired_deltas)
    paired_summary = {
        "pairs": len(paired_deltas),
        "unpaired_locations": unpaired,
    }
    for metric in (
        "rsrp_gain_db",
        "sinr_gain_db",
        "dl_gain_mbps",
        "ul_gain_mbps",
        "latency_reduction_ms",
        "packet_loss_reduction_pct_points",
        "outage_reduction_pct_points",
    ):
        paired_summary[metric] = (
            _mean(delta[metric] for delta in paired_deltas) if paired_deltas else None
        )

    ready = bool(paired_deltas)
    if ready:
        reason = "paired baseline and passive locations are available"
    elif rows:
        reason = "baseline and passive samples do not share a segment_id and seat_id"
    else:
        reason = "no samples have been collected"

    return {
        "schema_version": SCHEMA_VERSION,
        "ready": ready,
        "reason": reason,
        "total_samples": len(rows),
        "conditions": {
            condition: _condition_summary(condition_rows)
            for condition, condition_rows in by_condition.items()
        },
        "paired": paired_summary,
    }


class MeasurementStore:
    """Thread-safe bounded memory index backed by append-only JSONL evidence."""

    def __init__(self, path: str | Path, *, max_samples: int = 50_000) -> None:
        if max_samples <= 0:
            raise ValueError("max_samples must be positive")
        self.path = Path(path)
        self.max_samples = max_samples
        self._lock = threading.RLock()
        self._samples: list[dict[str, Any]] = []
        self._identities: set[tuple[str, str, int]] = set()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        with self.path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    sample = validate_sample(json.loads(line))
                except (json.JSONDecodeError, ValueError) as exc:
                    raise ValueError(
                        f"invalid evidence at {self.path}:{line_number}: {exc}"
                    ) from exc
                identity = (sample["run_id"], sample["condition"], sample["sequence"])
                if identity in self._identities:
                    raise ValueError(
                        f"duplicate evidence identity at {self.path}:{line_number}: {identity}"
                    )
                if len(self._samples) >= self.max_samples:
                    raise OverflowError("existing evidence exceeds max_samples")
                self._samples.append(sample)
                self._identities.add(identity)

    def add(self, sample: Mapping[str, Any]) -> bool:
        """Persist a sample. Return False for an already accepted identity."""

        normalized = validate_sample(sample)
        identity = (
            normalized["run_id"],
            normalized["condition"],
            normalized["sequence"],
        )
        with self._lock:
            if identity in self._identities:
                return False
            if len(self._samples) >= self.max_samples:
                raise OverflowError("measurement store is full")
            encoded = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
            with self.path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(encoded + "\n")
                handle.flush()
            self._samples.append(normalized)
            self._identities.add(identity)
            return True

    def snapshot(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(sample) for sample in self._samples]

    def status(self) -> dict[str, Any]:
        with self._lock:
            conditions = Counter(sample["condition"] for sample in self._samples)
            sources = Counter(sample["source"] for sample in self._samples)
            runs = {sample["run_id"] for sample in self._samples}
            latest = max(
                (sample["timestamp_utc"] for sample in self._samples), default=None
            )
            return {
                "status": "ok",
                "sample_count": len(self._samples),
                "max_samples": self.max_samples,
                "run_count": len(runs),
                "conditions": dict(sorted(conditions.items())),
                "sources": dict(sorted(sources.items())),
                "latest_timestamp_utc": latest,
                "evidence_path": str(self.path),
                "local_prototype": True,
            }

    def report(self) -> dict[str, Any]:
        return build_report(self.snapshot())
