# Evidence model and claim boundaries

Velocity Connect uses an evidence ladder. Each layer answers a different
question, and no layer automatically validates the one above it.

## Evidence ladder

| Level | Evidence | What it can support | What it cannot support |
|---:|---|---|---|
| 1 | Unit and integration tests | implementation behavior, input rejection, deterministic calculations | RF performance or railway service |
| 2 | Compact solved fixtures | matrix loading, reciprocity, passivity checks, delay and mapping logic | a fabricated antenna or installed coach path |
| 3 | Native HFSS project and converged solve | solver-specific electromagnetic behavior for the modeled geometry | measurement agreement, installation loss, field performance |
| 4 | ns-3/5G-LENA campaign | packet and mobility behavior under declared channel assumptions | measured route performance or product qualification |
| 5 | VNA, chamber, or OTA measurements | physical behavior of the measured prototype and setup | moving railway performance outside the measured setup |
| 6 | Instrumented coach and route trial | performance for the tested installation, route, load, and operating conditions | universal deployment performance or certification |

## Current project position

### Established in the repository

- CPU-level implementation behavior is covered by automated tests.
- Required source and compact evidence files are protected by a byte-level
  manifest.
- The transaction-v3 scalar-hypothesis network campaign has terminal ledgers
  for 816 successful runs.
- Balanced and delayed four-port fixtures are loadable, reciprocal, and
  contractive within the retained numerical checks.
- The bounded complex-transfer interface executes with explicit external
  operators in static single-stream validation.
- The local prototype validates and stores paired baseline/passive telemetry.

### Explicitly unresolved

- The retained radiator power audit reports native efficiency above 100
  percent. Absolute antenna gain and radiation efficiency are therefore
  inadmissible.
- The moving network experiment does not import the complex four-port,
  polarization, embedded patterns, cabin Green function, or coherent direct
  and passive paths.
- External coupling operators are not calibrated from a route measurement
  package.
- No fabricated feedthrough, VNA, chamber, installed-coach, passenger-loading,
  or moving-train result is included.
- Passing software tests does not establish manuscript acceptance or product
  readiness.

## How evidence is admitted

### Source and fixture evidence

`scripts/verify_source_manifest.py` compares every required file with the
reviewed byte count and SHA-256 digest. A mismatch is a hard failure until the
change is reviewed and the manifest is deliberately regenerated.

### Campaign evidence

A campaign must have a predeclared design, unique identities, isolated output
directories, terminal row status, complete factor coverage, and retained
failure history. Partial ledgers and resource pilots are not analyzed as
performance evidence.

### Electromagnetic evidence

Passive checks use raw complex coefficients or independently exported power
terms. Values are not clipped to physical bounds. A failed power-closure test
blocks gain and efficiency claims even if matching, isolation, TARC, or solver
convergence appears favorable.

### Measurement evidence

The admission contract checks schema, hashes, units, support, identifiers, and
passive bounds. Human review must still confirm instrument calibration,
fixture de-embedding, sampling design, route provenance, and authority to use
the data.

## Promotion gates

The complete product claim requires all of the following:

1. a power-closed integrated electromagnetic model containing both antennas,
   feedthrough, connectors, coach structure, liner, and representative cabin
   loading;
2. fabricated hardware with VNA and chamber measurements;
3. installed loss and polarization measurements on a representative coach;
4. route-calibrated moving coupling operators;
5. repeated baseline/passive network trials under matched route, load, and
   mobility conditions; and
6. statistical analysis that preserves failures and predeclared endpoints.

Until these gates are complete, the repository supports conditional simulation
and implementation claims only.

## Language for papers and reports

Use precise layer names:

- "software validation passed" for automated implementation tests;
- "HFSS simulation" for solver outputs;
- "system-level simulation" for ns-3/5G-LENA results;
- "measurement" only for instrument-derived data; and
- "field validation" only for a documented coach or route trial.

Avoid "validated product," "deployment ready," "measured gain," or "real-time
railway performance" unless the corresponding physical gate has been completed.

## Related

- [Architecture](architecture.md)
- [Evidence ledger](../RESULTS.md)
- [Revision 06 status](../reproducibility/REVISION06_STATUS.md)
- [Radiator power audit](../reproducibility/radiator_power_revision05.md)

[Back to the project overview](../README.md)
