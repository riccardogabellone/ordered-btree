# Executed validation and limits

## Executed release record — 0.1.0, 2026-09-24 UTC

Version 0.1.0 was published from tag `v0.1.0`, which points at protected-`main`
squash commit `430a5bdf109145f859b80f854f3329822124b6c2`. The release workflow
(GitHub Actions run 35942881278) ran the reusable CI for that exact commit, built
one wheel/sdist pair, published it to TestPyPI, verified the indexed bytes and a
clean isolated installation, paused for the owner's `pypi` environment approval,
then published the same bytes to PyPI with Sigstore attestations.

Hosted CI on GitHub-hosted `ubuntu-latest` and `windows-latest` runners passed
three times on this source: the pull request (run 35941314679), `main` after the
merge (run 35942554654) and the release tag (run 35942881278). Each run executed
all eight configurations — CPython 3.12, 3.13, 3.14 and free-threaded 3.14 on
both platforms — with **314 non-stress tests per configuration, zero failures,
errors or skips, and 100% runtime coverage**, plus the separate exhaustive test,
full standalone stress, lint/type checks, artifact build/verification and the
immutable-artifact handoff check. The fail-closed `CI required` check from the
GitHub Actions app is the merge gate; it emitted a success for every run.

Verified published files, identical on TestPyPI, PyPI and the GitHub release:

```text
2f3532455b266cd66f06893da5a26dd3a76f2945be43ed5b8ebba29d607aff1a  ordered_btree-0.1.0-py3-none-any.whl
6dd2dcf5068e92c590a096abf288809e99b338cf3d806b2e1d6704e972481caf  ordered_btree-0.1.0.tar.gz
acb347b1a303217116f2f13528fcc8b4c6be3f307fc18130c4d099f4844c87cc  manifest.json
```

The published metadata has no `Requires-Dist`, and its project URLs point back
to this repository. The repository homepage points to the PyPI project.

**Incident:** the first `verify-pypi` attempt failed at 01:36:30 UTC because the
exact-version JSON endpoint was not yet visible within the one-minute retry
window; the upload itself had returned `200 OK` for both files at 01:35:20 UTC.
Public endpoints served the release by 01:39:14 UTC. Only the failed
verification and the dependent GitHub-release finalization were rerun; no file
was rebuilt, re-uploaded or retagged. The post-upload visibility window was
subsequently extended to a bounded five-minute budget (see
[releasing](releasing.md)). Raw run logs, downloaded artifacts and parent-side
index checks are retained locally under `results/github-ci/`,
`results/github-release/` and `results/release-deployment/`; they are not
committed.

Limits of this record: hosted runners cover x86-64 Linux and Windows only; no
macOS, ARM64 or PyPy execution. Passing the free-threaded suite is not a
shared-instance thread-safety certification. Publication proves the artifact
provenance chain, not the absence of defects outside the tested contracts.

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
of publication. The hosted CI runs and the publication itself are recorded in the
executed release record above; this local record is retained unchanged as the
evidence it was at the time. Follow [releasing](releasing.md) for the current gates.
