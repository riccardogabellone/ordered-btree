# Executed validation and limits

## Dated local candidate record — 2026-09-23 UTC

This record predates the public 0.1.0 release preparation. It remains evidence
for the unchanged runtime, not a claim that the new release workflow ran or that
packages are available on an index. Current release gates are described in
[releasing](releasing.md).

This record describes executed checks, not merely a configured workflow. The
runtime, tests and verification tools were copied into isolated source directories;
the source hash maps did not change during either final platform run. Public
release documentation was finalized afterward. Final artifact/source manifests
associate the delivered files with these runs and the separate packaging checks.

| Platform | CPython | GIL | Non-stress suite | Exhaustive pytest | Runtime coverage |
| --- | --- | --- | --- | --- | --- |
| Windows 11 x86-64 | 3.12.10 | enabled | 257 passed | 1 passed | 100% |
| Windows 11 x86-64 | 3.13.11 | enabled | 257 passed | 1 passed | 100% |
| Windows 11 x86-64 | 3.14.7 | enabled | 257 passed | 1 passed | 100% |
| Windows 11 x86-64 | 3.14.7 free-threaded | disabled | 257 passed | 1 passed | 100% |
| Ubuntu / WSL2 x86-64 | 3.12.12 | enabled | 257 passed | 1 passed | 100% |
| Ubuntu / WSL2 x86-64 | 3.13.15 | enabled | 257 passed | 1 passed | 100% |
| Ubuntu / WSL2 x86-64 | 3.14.7 | enabled | 257 passed | 1 passed | 100% |
| Ubuntu / WSL2 x86-64 | 3.14.7 free-threaded | disabled | 257 passed | 1 passed | 100% |

No tests were skipped in those suites. `-m "not stress"` deselects the one
exhaustive test, which was then run separately. Coverage is **456 statements and
146 branches, all covered**, for the runtime package, not a coverage claim for
all developer tools. Coverage and stress testing are not proofs of correctness.

Windows build: 10.0.26200, MSVC-built CPython. Linux: Ubuntu userspace,
WSL2 kernel 6.6.87.2, glibc 2.35, Clang-built CPython. These are real separate
Windows/Linux interpreters; WSL validation is not a claim of native-Linux or
GitHub-hosted execution. Free-threaded runs explicitly used `PYTHON_GIL=0` and
checked both `Py_GIL_DISABLED` and `sys._is_gil_enabled()`.

## Checks executed

- Required Hypothesis state machine, seed **12983**, in every matrix entry;
  additional runs with seeds **34789** and **941337** passed on CPython 3.14.2.
- `<`-only/unhashable keys, first-representative identity, exception-position
  injection with exact structure/version fingerprints, reentrancy, no-op
  iteration, immutable structural snapshots, corrupt-structure detection and
  deterministic comparison-count checks.
- Populated threshold/grow/churn/drain/regrow histories, including degree 128;
  the small-tree randomized churn test remains as separate coverage.
- All **16** comparator-`StopIteration` cases passed after being observed failing:
  leaf/separator × `next`/`list` × base/subclass exception × comparison/truth conversion.
- Verification-tool regressions for optimized execution, stale reports, incorrect
  benchmark answers, metadata, unsafe archives, RECORD hashes and import isolation.
- Strict mypy in all eight environments; positive typing smoke and negative
  consumer checks for incompatible arguments and read-only properties/snapshots.
- Ruff lint and formatting across `src`, `examples`, `tests`, `tools`, `benchmarks`;
  `uv lock --check`; all three executable examples in every matrix entry.
- Standard PEP 517 frontend through uv, strict Twine validation, exact wheel/sdist
  inspection, clean external installs and independent extracted-sdist rebuild.
  Final deliverables are built/checked separately against the finalized source.
- Full deterministic benchmark, recorded separately in [performance](performance.md).
- Publication preflight deliberately returned **1**: private classifier,
  publication approval and live repository metadata remain gated.

## Full standalone stress, per matrix entry

| Workload | Executed amount |
| --- | --- |
| Exhaustive insertion/deletion orders, t=2, five keys | 14,400 histories; checked after every mutation |
| Random mixed operations | 540,000 operations, nine degrees, seeds 123/456/789 |
| Insertion/deletion order matrix | 64 histories × 4,000 keys, seed 567 |
| Large tree, t=32 | 100,000 inserts, 200,000 hit/miss probes, 5,000 ranges, 100,000 deletes; seed 9182 |

Random degrees: 2, 3, 4, 8, 16, 32, 64, 128, 256. The operation mix is 217,035
inserts, 161,487 deletes, 108,774 searches and 52,704 ranges. Every operation's
result is checked against an independent sorted-list model; full raw-node and
public-API cross-checks run every 257 operations and at the end.

The raw-node checker independently checks occupancy, child counts, identities,
local/inherited ordering, leaf depth and cardinality before cross-checking public
iteration and `validate()`. Deliberate corruption in tests is not supported usage.
The exhaustive pytest and standalone phases repeat the same workload; their
counts must not be added together as distinct histories.

## Tool versions and fingerprints

uv **0.12.15**, pytest **9.1.1**, Hypothesis **6.168.1**, coverage **7.16.1**,
mypy **1.20.2**, Ruff **0.16.8**, build **1.6.1**, Twine **6.2.0**.
The isolated build frontend resolved setuptools **84.0.0**. Full transitive
inventories are recorded per interpreter, and development resolutions are in
`uv.lock`; build requirements are resolved separately from that lock.

SHA256 of the tested runtime/configuration:

```text
e22ffb7d9e020816e07ddedd874f16989156eb7d605674dc00d91b82295ae5ef  src/ordered_btree/_tree.py
1a06d70c463c6df0e612aa593cac07670bc4212db839448b7c084818cd8574eb  src/ordered_btree/__init__.py
1bb0f5e7a4561622476191004ccf1d82d77c03195268fd5a80135b48e89a4e80  uv.lock
```

## Reproduction and retained evidence

From a source checkout, after `uv sync --locked`, a matrix entry uses the commands
below. Select the actual interpreter with `--python`; use separate
`UV_PROJECT_ENVIRONMENT` directories for concurrent versions. For `3.14+gil`
bootstrap, see [contributing](../CONTRIBUTING.md).

```bash
uv run --locked --python 3.14+gil coverage run --data-file results/run/.coverage -m pytest -q -m "not stress" --hypothesis-seed=12983 --junitxml=results/run/pytest.xml
uv run --locked --python 3.14+gil coverage report --data-file results/run/.coverage --fail-under=99
uv run --locked --python 3.14+gil coverage json --data-file results/run/.coverage -o results/run/coverage.json
uv run --locked --python 3.14+gil pytest -q -m stress
uv run --locked --python 3.14+gil python tools/stress.py --output results/run/stress.json
uv run --locked --python 3.14+gil mypy
```

Create a fresh `results/run/` first and never reuse report destinations. Exact
executed argv, start/end times, exit codes, logs, interpreter inventories, actual
imported-module hashes, per-file source maps, JUnit and coverage JSON are retained
locally under `results/rc-20260923/{windows,linux,quality,packaging}/`.
`results/candidate-benchmark/` contains the raw benchmark and its command record.
Raw machine-specific logs are intentionally excluded from Git and source packages;
the delivery evidence bundle retains them separately.

Initial setup failures and red regression runs were retained, not overwritten.
These included parent-workspace discovery, WSL shell/path adaptation, an unsupported
`+gil` download spelling, and a Windows environment-in-use replacement failure.
The final commands above passed after environment corrections; none was resolved
by suppressing tests. An unqualified `3.14` request was also found to select a
free-threaded installation, so final matrix entries explicitly distinguish the
ordinary and free-threaded builds rather than trusting a version label.

## Limits and release blockers

- Remote GitHub Actions, macOS, ARM64, PyPy and other Python builds were not run.
- No shared-instance concurrency certification: synchronization remains external,
  even when the free-threaded suite passes.
- Invalid comparator laws, ordering mutations, allocation failure and asynchronous
  interruption are outside the documented guarantees.
- Wall-clock measurements are shared-machine observations, not performance promises.
- At that run's date, public repository setup, live metadata/README URLs, index
  ownership and separate TestPyPI/PyPI authorization were outstanding. That local
  validation run performed no remote creation, push, tag, release or package upload.

Those results establish local verification of an identified candidate, not proof
of publication. The subsequent 0.1.0 preparation has live GitHub metadata and a
positive local release preflight; it does not retroactively turn this record into
remote CI evidence. Follow [releasing](releasing.md) for the current gates.
