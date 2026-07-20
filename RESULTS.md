# Evidence ledger

This ledger records completed terminal checks. A stability checkpoint is not a
multi-seed paper result and must not be presented as one.

## 2026-07-20 — paper-profile scheduler stability gate

Environment:

- ns-3 `3.46`
- CTTC 5G-LENA `v4.1.1` at `f29ebd33450c49af934ea5dde8606f855c22c2a6`
- Backported upstream production fixes:
  - beam-order heap overflow: `81892efac84f2aef0a962b9da176ea7d7b6912b0`
  - DL HARQ symbol-budget underflow: `a1aa32c757e0f834a4e40654853ce56dee13eca3`
- GCC `11.4`

Dependency regression:

```text
PASS: TestSuite nr-test-sched-harq
1 of 1 tests passed (1 passed, 0 skipped, 0 failed, 0 crashed)
```

Project checkpoint:

```bash
python3 verify_paper_checkpoint.py \
  --ns3 /home/codex/velocity-connect-ns3/ns3 \
  --workdir /home/codex/velocity-connect-ns3 \
  --out out/paper-checkpoint-fixed2
```

All three runs use 500 km/h, 500 m, 10 UEs, seed 7, 2 s simulation, 1024-byte
UDP packets, and 8.19 Mbps offered load per UE.

| Scenario | Status | Throughput (Mbps) | PDR | Mean latency (ms) | P95 latency (ms) |
|---|---:|---:|---:|---:|---:|
| metal | completed | 0.000000 | 0.000000 | unavailable | unavailable |
| composite | completed | 80.478738 | 0.994608 | 8.787140 | 12.688281 |
| repeater | completed | 80.694631 | 0.997276 | 4.756367 | 5.011483 |

The metal run received no packets, so latency is undefined rather than zero.
The result is evidence that the scheduler path is stable, not evidence that the
metal link provides service. The single-seed checkpoint validates execution
only; publication claims still require the declared multi-seed campaign.

Open parity item: the current live trace reports NR numerology 0, while the
submitted paper contract specifies 30 kHz SCS (numerology 1). Correct and
revalidate that configuration before running the full paper campaign.
