"""Send an explicitly synthetic paired A/B telemetry stream to the local prototype."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import random
import time
import uuid
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8765/api/v1/samples")
    parser.add_argument("--samples-per-condition", type=int, default=20)
    parser.add_argument("--interval", type=float, default=0.08)
    parser.add_argument("--seed", type=int, default=20260721)
    parser.add_argument("--speed-kmph", type=float, default=300.0)
    return parser.parse_args()


def post_json(url: str, payload: dict[str, object]) -> dict[str, object]:
    body = json.dumps(payload).encode("utf-8")
    request = Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(request, timeout=5.0) as response:
        return json.loads(response.read())


def main() -> int:
    args = parse_args()
    if args.samples_per_condition <= 0:
        raise SystemExit("--samples-per-condition must be positive")
    if args.interval < 0:
        raise SystemExit("--interval cannot be negative")

    rng = random.Random(args.seed)
    run_id = (
        datetime.now(timezone.utc).strftime("demo-%Y%m%dT%H%M%SZ-")
        + uuid.uuid4().hex[:8]
    )
    sequence = 0
    print("SYNTHETIC DEMO ONLY: these samples are not field or hardware evidence.")
    print(f"Run: {run_id}")

    try:
        for index in range(args.samples_per_condition):
            segment_id = f"segment-{index + 1:03d}"
            seat_id = f"{1 + index % 10}{'A' if index % 2 == 0 else 'D'}"
            baseline_rsrp = -111.0 + rng.uniform(-4.0, 4.0)
            baseline_sinr = -1.5 + rng.uniform(-2.5, 2.5)
            baseline_dl = max(0.0, 6.0 + rng.uniform(-4.0, 5.0))
            baseline_ul = max(0.0, 1.8 + rng.uniform(-1.0, 1.5))
            baseline_latency = 82.0 + rng.uniform(-16.0, 20.0)
            baseline_loss = min(100.0, max(0.0, 13.0 + rng.uniform(-7.0, 12.0)))

            for condition in ("baseline", "passive"):
                sequence += 1
                passive = condition == "passive"
                payload: dict[str, object] = {
                    "schema_version": "1.0",
                    "run_id": run_id,
                    "sequence": sequence,
                    "condition": condition,
                    "source": "demo",
                    "timestamp_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                    "segment_id": segment_id,
                    "seat_id": seat_id,
                    "speed_kmph": args.speed_kmph,
                    "latitude": 30.3165 + index * 0.0001,
                    "longitude": 78.0322 + index * 0.0001,
                    "rsrp_dbm": baseline_rsrp + (11.5 + rng.uniform(-1.5, 1.5) if passive else 0.0),
                    "sinr_db": baseline_sinr + (7.0 + rng.uniform(-1.0, 1.0) if passive else 0.0),
                    "dl_mbps": baseline_dl + (28.0 + rng.uniform(-5.0, 5.0) if passive else 0.0),
                    "ul_mbps": baseline_ul + (8.0 + rng.uniform(-2.0, 2.0) if passive else 0.0),
                    "latency_ms": max(1.0, baseline_latency - (43.0 + rng.uniform(-6.0, 6.0) if passive else 0.0)),
                    "packet_loss_pct": max(0.0, baseline_loss - (11.0 + rng.uniform(-2.0, 2.0) if passive else 0.0)),
                }
                response = post_json(args.url, payload)
                print(
                    f"{segment_id} {seat_id} {condition:8s} "
                    f"accepted={response.get('accepted')} count={response.get('sample_count')}"
                )
                time.sleep(args.interval)
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"collector returned HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise SystemExit(f"collector unavailable: {exc.reason}") from exc

    collector = urlsplit(args.url)
    dashboard_url = f"{collector.scheme}://{collector.netloc}"
    print(f"Demo complete. Open {dashboard_url} to inspect the paired report.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
