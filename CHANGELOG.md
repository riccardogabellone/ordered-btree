# Changelog

## 0.1.0 — initial release preparation

Publication is complete only when the corresponding GitHub release and verified
PyPI files are available. This version retains pre-1.0 compatibility guidance.

### Library

- Generic, typed ordered collection with `<`-only, first-wins key equivalence.
- Comparison-only search followed by comparator-free bottom-up mutation; failed
  comparisons and no-op updates preserve contents, structure and iterator validity.
- Private mutable nodes, read-only degree, detached immutable structural snapshots
  and shallow copies sharing key references.
- Iterative bisected range cursors, eager version capture, fail-fast iteration,
  explicit reentrancy errors and bounded representation.
- Upper-bound comparator `StopIteration` is chained through `RuntimeError`, avoiding
  silent truncation while retaining the unconsumed candidate for retry.
- One-pass shape-first validation, cycle/shared-node detection and strict degree
  validation. External synchronization is required for shared instances.

### Verification and development

- uv-managed environments, committed `uv.lock`, standard development dependency
  group and Python 3.14 development default; Python 3.12+ compatibility retained.
- Strict typing, lint/format checks, required Hypothesis, populated-tree histories,
  comparison-failure injection and independent model/structure validation.
- Stress and benchmark tools reject optimized execution, refuse reused report
  destinations, record loaded-source fingerprints and preserve explicit failures.
- Benchmark correctness checks compare individual lookup and range results outside
  timed regions instead of accepting only matching aggregate counts.
- Archive/metadata/RECORD checks, external uv-environment wheel installation,
  import-origin verification and independent sdist-to-wheel round trips.
- MIT licensing, name-only authorship and exact repository/documentation links.
- Protected-main release provenance, fail-closed required CI, immutable artifact
  handoff and separate direct TestPyPI/PyPI Trusted Publishing jobs with attestations.
- Exact-hash, missing-file-only recovery; official-index byte verification and
  token-free, no-dependency isolated installation before release finalization.
- Pinned setuptools build backend and checksum-pinned workflow syntax validation.

See [validation](docs/validation.md) for checks actually executed and limitations,
[compatibility](docs/migration.md) for integration guidance, and
[releasing](docs/releasing.md) for publication gates.
