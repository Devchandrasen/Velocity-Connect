# Velocity Connect productization plan

## Product decision

Build **Velocity Connect Rail Connectivity Validation System** before attempting a
rail-certified hardware product. The first buyer-facing outcome is an auditable
before/after coach connectivity report, produced from a passive RF feedthrough
prototype and synchronized measurements. It is not a passenger router, a powered
repeater, or an autonomous RAN controller.

The initial users are rolling-stock OEMs, rail operators, mobile operators, and
their system integrators. Their job is to determine whether a proposed coach
retrofit improves direct-to-device cellular service enough to justify a field
pilot and eventual certification.

## What already exists

- The ns-3/5G-LENA model provides controlled metal, composite, and passive-loss
  comparisons. Reuse it as a prediction source, not as field evidence.
- `research_campaign.py` already records configuration, failed runs, raw rows,
  confidence intervals, and provenance. Reuse its evidence discipline.
- `verify_paper_checkpoint.py` provides a deterministic execution gate. Retain it
  as a simulator regression check.
- `RESULTS.md` separates completed evidence from claim-ready evidence. Apply the
  same rule to hardware and live-radio trials.
- The current handover optimizer is synthetic. Do not connect it to a live RAN or
  describe it as a field-trained policy.

## v0.1 architecture

```text
Synthetic demo / modem adapter / ns-3 adapter
                    |
                    v
          POST /api/v1/samples
                    |
              validate schema
                    |
            reject / deduplicate
                    |
          +---------+----------+
          |                    |
          v                    v
  bounded memory store    append-only JSONL
          |
          +---------> paired calibration report
                                |
                                v
                     localhost dashboard
```

The v0.1 implementation uses Python's standard library so it starts on Windows
without another service or package install. Its HTTP server is intentionally a
local prototype and must not be exposed to an untrusted network. A production
service, authentication, TLS, and multi-user database are later-stage work.

The canonical telemetry sample contains:

- identity: schema version, run, sequence, condition, source;
- alignment: UTC timestamp, route segment, seat position, optional coordinates;
- operating state: speed;
- radio/service KPIs: RSRP, SINR, downlink, uplink, latency, packet loss.

Baseline and passive samples are paired by route segment and seat. A product
claim is not generated unless both conditions have measurements for the same
pairing key.

## Hardware prototype

The first assembly is a removable bench or parked-coach demonstrator, not a
rail-qualified roof installation.

| Item | Prototype requirement | Evidence produced |
|---|---|---|
| Donor antenna | Target-band 3.3-3.8 GHz, nominal 6-10 dBi | Datasheet plus measured return loss |
| Service antenna | Target-band indoor antenna, nominal 2-5 dBi | Datasheet plus measured return loss |
| Feeder | Short low-loss 50-ohm cable with known connectors | VNA insertion-loss trace |
| Feedthrough | Reversible bulkhead or protected test aperture | Mechanical and connector-loss record |
| RF instruments | VNA or calibrated two-port analyzer | S11/S22/S21 files and calibration record |
| Measurement UEs | Two identical 5G modems/phones where possible | Baseline/passive KPI streams |
| Position/time | GNSS when moving; labelled fixed positions on bench | Pairing and route alignment record |
| Test enclosure | Metal cabinet/mock coach first; parked coach second | Repeatable seat/position map |

Do not buy a permanent roof antenna or drill a coach until the target operator,
band set, mounting constraints, and test authorization are confirmed.

### Bench acceptance gate

- Measure and retain S11/S22 and end-to-end S21 across the target band.
- Target antenna return loss of at least 10 dB across the declared operating band.
- Record the real cable/feedthrough insertion loss; do not force it to match the
  paper's 3 dB assumption.
- Run baseline and passive conditions at no fewer than 20 labelled cabin points,
  with at least three repeated captures per condition.
- Require paired measurements and report median, fifth percentile, spread, and
  missing data. Never replace missing samples with simulated values.
- Treat 10 dB median RSRP gain, 50% outage reduction, and two-times fifth-percentile
  throughput as provisional pilot targets, not guaranteed specifications.

## Delivery phases and gates

### Phase 0 - v0.1 local measurement loop (now)

Deliver a validated telemetry contract, append-only evidence file, paired report,
synthetic demo stream, and live local dashboard.

Gate: all unit and HTTP integration tests pass; duplicate and invalid samples do
not alter evidence; the dashboard displays an explicit synthetic-data warning.

### Phase 1 - RF bench prototype (2-6 weeks, depends on equipment access)

Assemble donor antenna, feeder/feedthrough, and service antenna. Measure component
and end-to-end behavior before testing cellular KPIs.

Gate: retained VNA traces, calibration metadata, repeatable loss within 2 dB, and
no unexplained frequency notch in the target band.

### Phase 2 - private 5G lab (4-8 weeks)

Connect a COTS UE to a controlled 5G network and ingest modem plus network metrics.
Begin with one cell. Add a second cell only when independent RF chains or a suitable
commercial testbed are available.

Gate: three repeated baseline/passive sessions, complete provenance, live dashboard
delay below two seconds, and quantified downlink, uplink, and interruption behavior.

### Phase 3 - parked coach or rail yard (8-12 weeks)

Use a reversible installation, a fixed seat map, alternating A/B conditions, and
operator-approved non-passenger testing.

Gate: statistically credible paired improvement, installation repeatability, and
no observed degradation outside the intended coach area.

### Phase 4 - controlled route trial (3-6 months)

Run approved monitored trials with the operator and mobile-network partner. Record
GNSS, serving cell, handovers, RF KPIs, service KPIs, route conditions, and all
missing intervals. Keep the system monitoring-only.

Gate: route outage, fifth-percentile throughput, handover interruption, and model
error meet the agreed pilot thresholds without worsening handover failures.

### Phase 5 - rail-grade product (6-12 months after pilot evidence)

Complete environmental, EMC, vibration, fire/material, installation, maintainability,
manufacturing, and regulatory classification with rail and RF specialists.

## Test coverage map

```text
POST sample
  |-- malformed JSON ----------------> 400, visible error
  |-- invalid schema/range ----------> 400, visible error
  |-- first valid identity ----------> 201, memory + JSONL
  |-- duplicate run/condition/seq ---> 200 duplicate, no second write
  |-- storage full ------------------> 507, visible error
  `-- persistence failure -----------> 500, visible error

GET report
  |-- no samples --------------------> ready=false
  |-- one condition only ------------> ready=false, reason
  |-- unpaired locations ------------> excluded and counted
  `-- paired baseline/passive -------> directional improvement KPIs

Restart
  |-- valid JSONL --------------------> reload and preserve identity index
  `-- corrupt JSONL ------------------> fail loudly with line number
```

## Failure modes

| Failure | Handling | Test | User-visible |
|---|---|---|---|
| Duplicate modem delivery | Idempotent run/condition/sequence key | Yes | Accepted as duplicate |
| Out-of-range or missing KPI | Reject before persistence | Yes | HTTP 400 with field reason |
| Concurrent sample posts | Lock persistence and indexes | Yes | No corruption or silent loss |
| Store reaches configured cap | Reject new writes | Yes | HTTP 507 |
| Corrupt historical evidence | Abort startup with line number | Yes | Terminal error |
| Missing baseline/passive pair | Exclude from paired claim | Yes | Report states not ready/counts |
| Browser polls during no data | Return valid empty report | Yes | Waiting-for-data state |
| Server accidentally exposed | Default bind is 127.0.0.1 | Yes | Startup prints local URL/warning |

## NOT in scope for v0.1

- Live RAN parameter writes: monitoring must be proven safe before any control path.
- AI/DRL handover claims: there are no real corridor traces yet.
- Mission-critical FRMCS or railway signalling: this prototype targets passenger
  direct-to-device connectivity validation only.
- Public internet deployment: the standard-library server is local lab tooling.
- Rail-qualified mounting or certification: requires a coach, operator, and test lab.
- Universal multi-band passive hardware: first validate one declared target band.
- Purchasing or permanently modifying a train: partner constraints must be known first.

## Parallel execution

| Lane | Modules | Depends on |
|---|---|---|
| A | `prototype/` measurement software | None |
| B | RF hardware procurement and bench setup | Target band and equipment access |
| C | ns-3 multi-cell and explicit relay model | Existing simulator baseline |
| D | coach/route partnership and approvals | Buyer/operator engagement |

Lanes A, C, and D can proceed in parallel. Lane B can define candidate components
now but should not place irreversible orders until the band and installation context
are confirmed. Phase 2 integration waits for A and B.
