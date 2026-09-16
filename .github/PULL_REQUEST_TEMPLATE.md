## Purpose

Describe the problem and the narrow change that addresses it.

## Evidence layer

- [ ] Implementation only
- [ ] Compact electromagnetic fixture or audit
- [ ] Network simulation
- [ ] Measurement contract
- [ ] Documentation only

## Verification

List the exact commands and outcomes.

```text
python scripts/verify_source_manifest.py
python -m pytest -q
```

## Scientific integrity checklist

- [ ] I preserved failed and interrupted evidence.
- [ ] I did not promote a smoke test, fixture, or synthetic stream into a physical claim.
- [ ] I documented any changed seed, threshold, dependency pin, or acceptance rule.
- [ ] I added no credentials, private data, bulk outputs, or unauthorized solver files.
- [ ] New or changed local documentation links resolve.
