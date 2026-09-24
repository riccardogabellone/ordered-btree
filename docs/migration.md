# Compatibility and upgrades

## Supported environment

`ordered-btree` requires Python 3.12 or newer and has no runtime dependencies.
The import package is `ordered_btree`. Python 3.14 is the development default,
not a requirement imposed on applications. Use the installed distribution's
metadata for the version:

```python
from importlib.metadata import version

print(version("ordered-btree"))
```

The initial version is 0.1.0; the public API is **pre-1.0**, not a promise of 1.0
maturity. Pin a tested version in applications and read the
[changelog](../CHANGELOG.md) before upgrading. There is no stability promise for
underscore attributes, exact node layouts or diagnostic text formatting.

## Application integration

- Store immutable ordering-relevant state. Snapshots and copies share the same
  key objects; a frozen container does not make arbitrary keys deeply immutable.
- Search returns the actual stored equivalent representative, or `None`.
- Ordering uses only `<`; equivalence is not Python equality or hashing.
- The default minimum degree is two. Construct a new tree to change the degree.
- Use `inspect()` for detached structural diagnostics, not private storage.
- Iterate over `snapshot()` when a loop must mutate the tree. Do not catch an
  invalidation exception and assume the same iterator can resume.
- Hold an external lock across reads and complete iterator consumption when
  multiple callers share a mutable instance.

Bottom-up balancing may choose different valid shapes for different operation
histories. Applications must not depend on exact node placement. A structural
regression test should establish the fixture shape it intends to exercise.

## Comparator exceptions in iterators

Upper-bound comparison failures preserve the candidate for retry. `StopIteration`
from a comparator is special: it is wrapped in `RuntimeError`, with the comparator
exception in `__cause__`, so iteration consumers cannot mistake it for normal
termination. This also covers exceptions in truth conversion of the comparison
result. Other comparator exceptions propagate unchanged. Genuine exhaustion
and iterator invalidation remain permanent.

## Contributor environment

Use `uv sync --locked` and `uv run --locked ...`; no activation is required.
Development dependencies live in `[dependency-groups].dev`, not a published
`[dev]` extra. Standard Python packaging tools can still install/build the
library. Changing the environment manager does not change the runtime API.

See [contributing](../CONTRIBUTING.md) for checks and [releasing](releasing.md) for
artifact validation and publication safeguards.
