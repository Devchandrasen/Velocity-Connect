# HFSS validation fixtures

These Touchstone files are compact copies of the solved reciprocal four-port
exports used to validate the implementation:

- `PTF_V4_Balanced_Cross.s4p` is the balanced cross-connected control.
- `PTF_V5_Delay25ps_Cross.s4p` is the physically lengthened cross-connected
  candidate.

Port order is `D1, D2, S1, S2`. Intended cross transfers are `S41` and `S32`.
The fixtures are simulation outputs, not VNA measurements. Their hashes are
covered by `reproducibility/source_manifest.json`.
