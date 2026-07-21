# Velocity Connect validation prototype v0.1

This local prototype collects baseline and passive-relay measurements, preserves
them as append-only JSONL, computes paired before/after KPIs, and serves a live
dashboard. It does not control a network and the included stream is synthetic.

## Start the collector

From the repository root:

```powershell
python -m prototype.velocity_connect.server --data out/prototype/samples.jsonl
```

Open `http://127.0.0.1:8765`.

In another terminal, send a labelled synthetic A/B stream:

```powershell
python prototype/demo_stream.py --samples-per-condition 20
```

The server uses only the Python standard library. No new Python dependency is
required for this milestone.

## Run tests

```powershell
python -m unittest discover -s tests -v
```

## Sample contract

```json
{
  "schema_version": "1.0",
  "run_id": "yard-test-001",
  "sequence": 1,
  "condition": "baseline",
  "source": "modem",
  "timestamp_utc": "2026-07-21T03:00:00Z",
  "segment_id": "coach-A-position-01",
  "seat_id": "12A",
  "speed_kmph": 0,
  "latitude": null,
  "longitude": null,
  "rsrp_dbm": -108.5,
  "sinr_db": -1.2,
  "dl_mbps": 4.8,
  "ul_mbps": 1.1,
  "latency_ms": 71.0,
  "packet_loss_pct": 8.0
}
```

Allowed conditions are `baseline` and `passive`. Sources are `demo`, `ns3`,
`modem`, `scanner`, and `srsran`. Baseline/passive reports are paired by
`segment_id` and `seat_id`. Sample identity is `run_id + condition + sequence`,
so a retry is idempotent while each condition may maintain its own sequence.
The v0.1 outage flag is true when downlink is below 1 Mbps or packet loss is
above 10%; later pilots must freeze thresholds in the approved test protocol.

## Safety and claim boundary

- The server binds to `127.0.0.1` by default and has no production authentication.
- Do not expose it to an untrusted network.
- `source=demo` is always synthetic and must never be cited as field evidence.
- A paired report is a measurement summary, not a certification result.
- Do not connect this prototype to live RAN write/control interfaces.
