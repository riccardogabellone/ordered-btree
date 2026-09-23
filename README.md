# ordered-btree

A pure-Python, typed, generic **ordered collection of unique keys**, with a B-tree
storage engine. Python **3.12+**, including Python 3.14. No runtime dependencies.
Licensed under [MIT](LICENSE).

The distribution is `ordered-btree`; the import is `ordered_btree`. This is an
unpublished alpha. Install from source or a locally built wheel, not by querying
PyPI for this name. Package publication is explicitly gated; see
[releasing](docs/releasing.md).

## Highlights

- Private mutable nodes; read-only degree; detached frozen diagnostic snapshots.
- Only `<` is required. Unhashable keys and keys without usable `==` work.
- A single comparison-only search precedes comparator-free updates. Raising
  comparisons leave contents, structure, size, and iterator validity unchanged.
- Iterative traversal and bisected range seeking, with fail-fast iterators.
- One-pass structural validation, including cycles, shared nodes, bounds and size.
- Tests, fault injection, exhaustive/randomized stress, deterministic benchmarks,
  wheel/sdist packaging, `py.typed`, and CI configuration.

**Validation:** see [the validation record](docs/validation.md) for exact executed
runtimes, commands, results and limitations. Configured CI is not evidence that a
remote run has completed. See [contributing](CONTRIBUTING.md) for development and
[security](SECURITY.md) for the security policy.

## Install from the project directory

Use [uv](https://docs.astral.sh/uv/getting-started/installation/) 0.12.15 or newer.
The following commands work from the project directory on Windows, Linux and
macOS; no shell activation is needed:

```bash
uv sync --locked                   # Development environment, Python 3.14 by default
uv run --locked python examples/basic.py
```

To install just the library into a separate application environment:

```bash
uv venv --python 3.14
uv pip install /path/to/ordered-btree
# Or install a locally built wheel without runtime dependencies:
uv pip install --no-deps /path/to/ordered_btree-0.1.0a1-py3-none-any.whl
```

Ordinary `python -m pip install /path/to/ordered-btree` also works: uv is a
contributor tool, not a requirement for applications using the library. Python
3.12 and 3.13 remain supported. The project's Python pin selects a development
default; it does not raise the minimum version.

Do **not** run `uv pip install ordered-btree` expecting this unpublished project.
A missing index listing does not reserve a name or establish ownership.

## Basic usage

```python
from ordered_btree import BTree

numbers = BTree[int](t=32, keys=[10, 20, 5, 6, 12, 30, 7, 17])

assert list(numbers) == [5, 6, 7, 10, 12, 17, 20, 30]
assert list(numbers.range(6, 18)) == [6, 7, 10, 12, 17]  # [start, stop)
assert list(numbers.range(None, 7)) == [5, 6]
assert list(numbers.range(20, None)) == [20, 30]

assert numbers.search(6) == 6       # Stored representative, not a node.
assert numbers.search(999) is None
assert 12 in numbers
assert numbers.insert(6) is False  # Equivalent key already present.
assert numbers.delete(12) is True
assert numbers.delete(999) is False

assert numbers.min() == 5
assert numbers.max() == 30
assert numbers.pop_min() == 5
assert numbers.pop_max() == 30
numbers.validate()
```

`t` is the minimum degree, not the maximum number of keys. A node holds at most
`2*t-1` keys. The default remains `t=2` for compatibility. `t=32` in these examples
is an explicit starting point to benchmark, not a universally optimal default.
Floats (including `2.0`), booleans, strings, NaN, and infinity are rejected as
**degrees**. Invalid integer degrees below two raise `ValueError`.

## Custom immutable records

```python
from __future__ import annotations
from dataclasses import dataclass
from ordered_btree import BTree

@dataclass(frozen=True, slots=True)
class Job:
    priority: int
    job_id: int
    description: str = ""

    def __lt__(self, other: Job) -> bool:
        return (self.priority, self.job_id) < (other.priority, other.job_id)

first = Job(1, 42, "Original payload")
jobs = BTree[Job](keys=[first, Job(3, 12, "Later")])
probe = Job(1, 42, "Different payload")

assert probe != first                 # Dataclass equality sees the payload.
assert jobs.insert(probe) is False    # BTree ordering does not.
assert jobs.search(probe) is first     # First equivalent representative wins.
assert jobs.pop_min() is first
```

Ordering must be a **stable strict weak ordering** across all stored keys and
probes. Keys are equivalent when neither is less than the other. No `==`, `<=`,
`>`, `>=`, or hashing is used internally. `None` is reserved for missing results
and open range bounds and cannot be stored. NaN **keys**, partial orders, and
inconsistent comparators are unsupported; arbitrary comparator laws are not
validated automatically. In particular, this implementation does not promise to
recognize and reject every invalid key before insertion into an empty tree.

Frozen dataclasses help, but Python does not enforce Rust-style ownership.
Nested values may remain mutable, and the tree retains the exact objects passed
in. Never change ordering-relevant state while a key is stored. Use an immutable
replacement and an explicit delete/insert operation instead. Mutable payloads
are acceptable only when they cannot affect ordering. Range-bound objects must
also remain stable until iteration ends.

## Mutation and iteration

```python
from ordered_btree import BTree, ConcurrentModificationError

tree = BTree[int](keys=[1, 2, 3])
iterator = iter(tree)           # Version captured immediately.
assert next(iterator) == 1

tree.insert(4)
try:
    next(iterator)
except ConcurrentModificationError:
    print("Create a new iterator, or iterate over a snapshot.")
```

Successful insertion, deletion, clearing, and extreme removal invalidate active
iterators. Duplicate insertion, missing-key deletion, and clearing an empty tree
are genuine no-ops and **do not** invalidate them. Deleting and reinserting the
same key still invalidates an iterator even if the size is unchanged.

Mutation before the first `next()` is detected. Once an iterator has raised
`StopIteration`, it stays exhausted. After a modification error it is also
exhausted. Iterator creation/lower-bound comparisons happen eagerly; comparisons
against the upper bound happen as results are consumed. An upper-bound
comparison exception leaves its candidate unconsumed, so it can be retried after
the comparator is repaired. A `StopIteration` raised by that comparison is wrapped
in `RuntimeError` with the original exception as its cause: comparator failure
must not look like normal iterator exhaustion. Other comparison errors propagate.

```python
stable_values = tree.snapshot()  # tuple of keys, detached from future updates
shape = tree.inspect()           # frozen NodeSnapshot; tuples of child snapshots
clone = tree.copy()              # independent mutable nodes, same key objects

for key in tree.snapshot():
    tree.delete(key)             # Safe: iterating over the detached tuple.
```

Snapshots are **structurally immutable, not deep copies**. `search`, `min`, `max`,
iteration, snapshots, and `copy` all share key references. There is no public live
`root`, and there is no public mutable node class. Underscore attributes are
implementation details, not a security boundary against deliberate tampering.

## API at a glance

| API | Result / behavior |
| --- | --- |
| `BTree[T](t=2, keys=None)` | Incrementally consumes keys; keeps first equivalent object |
| `insert(key)` | `True` if inserted, otherwise `False` |
| `delete(key)` | `True` if removed, otherwise `False` |
| `search(key)` | Stored equivalent key or `None`; never a node |
| `key in tree`, `len(tree)`, `bool(tree)` | Membership by ordering, size, non-emptiness |
| `min()`, `max()` | Stored extreme or `None` |
| `pop_min()`, `pop_max()` | Remove/return extreme; `KeyError` when empty |
| `iter(tree)` | Ascending, fail-fast iterator |
| `range(start=None, stop=None)` | Half-open `[start, stop)`; no bounds means full scan |
| `snapshot()` | Detached sorted tuple; shallow |
| `inspect()` | Detached frozen recursive `NodeSnapshot`; shallow keys |
| `copy()`, `copy.copy(tree)` | New mutable nodes, shared keys; no comparisons |
| `clear()` | Empty the tree; returns `None` |
| `height()` | Levels, zero when empty |
| `validate()` | `None` if valid; `ValueError` for structural corruption |
| `format_tree()`, `display(file=...)` | Diagnostic text / printing |
| `t`, `min_keys`, `max_keys` | Read-only properties |

This is not a `collections.abc.MutableSet` subclass: unordered set equality and
hash-based equivalence would suggest semantics this library does not implement.
There are no set operators, map values, multiset counts, rank/select operations,
key-projection callback, persistence layer, or bulk-transaction API.

## Exception and concurrency contracts

For ordinary exceptions raised by comparisons, single-key `insert` and `delete`
have a strong no-change guarantee: all comparisons finish before mutation. No-op
updates are equally non-mutating. Replacement extraction, borrowing, merging,
and root contraction do not compare keys. Invalid-type comparison errors propagate.

This is **not** a transaction against allocation failure, `KeyboardInterrupt`,
process termination, or malicious callbacks changing private state. Commit-time
allocation failure/interruption can leave the tree unusable; rebuild it from a
trusted external source. Construction is incremental, not a bulk transaction.
`validate()` detects structure errors but cannot prove comparator laws; exceptions
from its comparisons propagate rather than being relabeled as corruption.

Public content operations reject same-tree re-entrancy with
`ReentrantOperationError`, including callbacks trying to read the tree during an
active comparison. Constant-time metadata (`len`, degree and occupancy limits)
can be read in callbacks. Callbacks may operate on a different tree.

There is **no thread-safety guarantee**, with or without the GIL. The re-entrancy
flag and iterator version are not locks. All callers sharing a mutable instance
must use an external lock, including around reads and the entire consumption of
an iterator. See [the synchronization example](examples/synchronized.py).

## Complexity and performance

Let `h` be height, `t` minimum degree, `n` stored keys, and `k` returned keys.
Comparison costs are assumed constant; expensive comparators add their own cost.

| Operation | Cost |
| --- | --- |
| Search / membership | `O(h log t)` comparisons; `O(1)` auxiliary storage |
| Insert / delete | `O(h log t)` comparisons + `O(t h)` worst-case list movement; `O(h)` retained path |
| Range | `O(h log t + k)` total traversal/comparison work; `O(h)` cursor storage |
| Full iteration | `O(n)` total; `O(h)` cursor storage |
| Min / max / height | `O(h)` |
| Pop min / max | No comparisons; `O(t h)` worst-case list movement |
| Length | `O(1)` |
| Snapshot / inspect / copy | `O(n)` time and output storage |
| Validate | `O(n)` time; `O(number of nodes)` identity tracking |
| Repr | Visits at most nine keys: `O(h + 9)`, plus eight key representations |

Splits also use `O(t)` temporary list storage. The range bound includes amortized
successor traversal, not a promise that every individual `next()` is `O(1)`.
Clearing may perform `O(n)` reference releases, subject to outstanding references
and garbage collection. Keys and their callbacks may have additional costs.

Faster asymptotics do not guarantee faster wall-clock performance for every
workload. Fail-fast checks and Python iterator dispatch have a cost, particularly
for full scans with large nodes. [Performance measurements](docs/performance.md)
record deterministic inputs, actual runtimes and limitations. Degree should be
selected using your own comparator, key sizes, and operation mix.

## Development and tests

```bash
uv sync --locked
uv run --locked pytest -q -m "not stress"
uv run --locked pytest -q -m stress
uv run --locked python tools/stress.py
uv run --locked python benchmarks/benchmark.py
uv run --locked coverage run -m pytest -q -m "not stress"
uv run --locked coverage report --fail-under=99
uv run --locked mypy
uv run --locked ruff check src examples tests tools benchmarks
uv run --locked ruff format --check src examples tests tools benchmarks
uv run --locked python examples/basic.py
uv run --locked python examples/records.py
uv run --locked python examples/synchronized.py
```

`tools/stress.py --quick` is a shorter deterministic run. Hypothesis is installed
by the development dependency group and is required for the property tests.
Verification tools reject optimized Python (`-O` / `PYTHONOPTIMIZE`), use fresh
report destinations and record failures rather than reusing stale success data.
Raw reports and local agent files are intentionally not committed.

Build into a **new** directory and independently exercise the artifacts:

```bash
uv build --no-create-gitignore --out-dir dist/candidate
uv run --locked twine check --strict dist/candidate/*
uv run --locked python tools/verify_dist.py dist/candidate
```

The artifact verifier checks metadata, archive contents, `py.typed` and hashes,
installs the wheel in an external temporary uv environment, and independently
rebuilds and exercises a wheel from the extracted sdist. Publication is a separate,
intentional step; follow [the release checklist](docs/releasing.md).

## Project map

```text
src/ordered_btree/    Runtime implementation, public exports, py.typed
examples/            Executable basics, immutable records, external locking
tests/               API, mutation, exception safety, independent model checks,
                     property tests, and verification-tool regressions
tools/               Stress, isolated artifact checks and publication preflight
benchmarks/          Deterministic workload measurements with raw samples
docs/                Design, compatibility, validation, performance and releases
.github/             CI, dependency updates and contribution templates
```

## Scope and release status

The library deliberately uses private mutable nodes, shallow immutable snapshots,
first-wins ordering equivalence, fail-fast iteration, explicit external locking,
`None` reserved, and Python 3.12+ compatibility. See [design](docs/design.md) and
[compatibility](docs/migration.md) before depending on alpha API stability.

The project is MIT licensed. The matching repository/distribution name is chosen,
but remote repository creation and package publication have not been authorized.
`Private :: Do Not Upload` remains in package metadata. Building and verifying
local artifacts does not remove that safeguard.
