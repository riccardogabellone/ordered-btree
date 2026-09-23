# Performance measurements

## Recorded workload

Measured on **CPython 3.14.2, GIL enabled, Windows 11 x86-64** on 2026-09-23 UTC,
using the candidate runtime below. Three repetitions per degree, deterministic
seed **34789**, garbage collection enabled and collected before each repetition.
These are **median total milliseconds**, not per-operation latency.

- 100,000 unique integers inserted in shuffled order.
- 50,000 mixed hit/miss membership probes.
- 100,000 deletions in shuffled order.
- 5,000 width-ten ranges in the upper 10% of the key space.
- One complete scan and one representation per repetition.

| t | Insert | Probe | Delete | Ranges | Full scan | Repr |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2 | 311.9 | 89.2 | 339.2 | 31.1 | 28.4 | 0.031 |
| 8 | 146.2 | 45.6 | 178.3 | 20.0 | 17.5 | 0.028 |
| 32 | 103.1 | 36.4 | 125.1 | 18.0 | 15.8 | 0.025 |
| 128 | 96.3 | 32.0 | 98.0 | 17.1 | 13.9 | 0.024 |
| 512 | 91.3 | 27.3 | 98.4 | 15.9 | 15.1 | 0.023 |

Raw samples, exact argv, runtime/build details and loaded-source fingerprints are
retained with the local validation evidence in
`results/candidate-benchmark/benchmark.json`. Raw run files are not committed.
Runtime `_tree.py` SHA256:
`e22ffb7d9e020816e07ddedd874f16989156eb7d605674dc00d91b82295ae5ef`.

## Interpretation and limits

There is no universally optimal degree. Larger nodes reduce tree depth but add
list movement and may have worse cache/comparison costs for different key types.
The default remains `t=2`; application examples choosing `t=32` do not change it.

Fail-fast/version and reentrancy checks remain enabled in every timed operation.
Full-scan costs are reported alongside narrow-range timings; safety checks are
not bypassed for benchmark speed. Bisection and bounded representation also have
deterministic comparison-count regression tests, independent of wall-clock noise.

Measurements ran sequentially on a shared machine, without CPU isolation,
confidence intervals or a statistical benchmark framework. Variability is visible
in the raw samples. These numbers do not establish speedups, universal throughput,
or performance on another Python build, operating system, key type or workload.
They are not free-threaded performance measurements.

Input generation, per-result correctness checks, validation and memory accounting
are outside timed regions. Each membership result and exact range output is
checked independently; matching only aggregate hit or result counts is not enough.
Stress durations include model/structure validation and are **not benchmarks**.

`structure_bytes_excluding_keys` sums node/list object sizes. It excludes key
storage, allocator metadata, peak temporary allocation and process RSS.

## Reproduce

For the recorded command, use a Python 3.14.2 environment:

```bash
uv run --locked --python 3.14.2 python benchmarks/benchmark.py --n 100000 --probes 50000 --ranges 5000 --repeats 3 --degrees 2 8 32 128 512 --output results/my-benchmark/benchmark.json
```

Or measure the interpreter selected for the current project:

```bash
uv run --locked python benchmarks/benchmark.py --repeats 5
```

Inspect the recorded interpreter/build/GIL state rather than inferring it from a
minor-version request. Omit `--output` for a unique timestamped destination; an
existing explicit output path is refused. The runner rejects `-O`/`-OO` and
`PYTHONOPTIMIZE`, records a started result before work, and records a terminal
failed status if validation fails. Atomic initial publication requires a filesystem
supporting hard links; unsupported filesystems fail safely rather than overwrite
existing evidence.
