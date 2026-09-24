# Contributing

This is a pre-1.0, dependency-free Python library. Please read the
[design](docs/design.md) and [migration notes](docs/migration.md) before changing
behavior. Contributions are provided under the [MIT license](LICENSE); include
only material you have permission to contribute.

## Development with uv

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) 0.12.15 or
newer, then, from this directory:

```bash
uv sync --locked
uv run --locked pytest -q -m "not stress"
uv run --locked pytest -q -m stress
uv run --locked ruff check src examples tests tools benchmarks
uv run --locked ruff format --check src examples tests tools benchmarks
uv run --locked mypy
uv run --locked coverage run -m pytest -q -m "not stress"
uv run --locked coverage report --fail-under=99
uv run --locked python examples/basic.py
uv run --locked python examples/records.py
uv run --locked python examples/synchronized.py
```

Python 3.14 is the local default; the library's minimum is 3.12. To exercise
another interpreter, use `uv run --locked --python 3.12 pytest -q`. Separate
`UV_PROJECT_ENVIRONMENT` directories avoid repeatedly replacing `.venv` when
running a matrix. When both Python 3.14 variants are installed, use `3.14+gil` for
the ordinary build and `3.14t` for the free-threaded build, and check the actual
GIL/build state. With uv 0.12.15, bootstrap the ordinary interpreter first using
`uv python install 3.14`: `+gil` selects an installed build but is not a downloadable
variant spelling in that uv version. CI handles this bootstrap explicitly.
Hypothesis is required in development, not an optional skipped check. Run
verification without `-O`, `-OO`, or `PYTHONOPTIMIZE`.

The committed `uv.lock` pins development tools, not consumer dependencies. Change
constraints in `pyproject.toml` deliberately and regenerate the lock using
`uv lock`; for a targeted update use `uv lock --upgrade-package <name>`. Commit
both files and re-run the checks. Do not hand-edit the lock. Development tools
are a standard dependency group; use `uv sync`, not an installation of
`ordered-btree[dev]`. The build backend is pinned separately in `[build-system]`;
update that pin deliberately and repeat the independent artifact round trip.

## Changes and regression tests

- Reproduce a defect with a failing test before fixing it.
- Preserve `<`-only ordering, first-wins equivalence and shallow key ownership.
- Do not add comparisons to structural mutation or invalidate iterators on no-ops.
- Preserve reentrancy and fail-fast checks; they are not locks.
- Keep the independent raw-node checker and comparison-failure injection.
- Changes to APIs, runtime dependencies, locking, ownership or duplicate semantics
  need a separate design discussion, not an incidental refactor.
- Update relevant docs/examples and CHANGELOG.md together with behavior changes.
- Run the standalone stress runner for balancing changes and the benchmark for
  performance changes. Use fresh result paths and the same runtime/input sizes;
  report regressions as well as improvements. See [validation](docs/validation.md)
  and [performance](docs/performance.md).

Lint and format only the directories in the commands above. Keep generated
validation logs and local working notes separate from the public documentation.

## Review and repository policy

Keep pull requests focused. Provide the reproducer, exact commands/runtime, and
actual results; disclose skipped checks. Do not submit credentials, caches,
environments, generated artifacts, local agent instructions or raw run logs.

Contribute through issues and fork pull requests. Only the owner or explicitly
trusted collaborators can merge upstream. Protected `main` requires a PR,
resolved conversations, an up-to-date branch and the exact **CI required** Actions
check; administrators have no bypass. There is no mandatory second reviewer,
which keeps ordinary PR merges usable by a solo maintainer.

CI runs on branch pushes, PRs and manual requests; release tags call the same CI
for their exact commit. The required aggregate fails on failure, cancellation or
unexpectedly skipped jobs. Workflow syntax (including the normally dormant release
workflow) is checked with checksum-pinned actionlint. Untrusted PR code gets no
write permissions, publishing identity or package credentials. These controls
also depend on remote rules/environment settings; files alone do not enable them.

The source archive omits GitHub configuration; use a repository checkout or
project ZIP for repository administration. Build verification still works from
the source archive.

## Releases

Follow [releasing](docs/releasing.md). A successful local build or metadata check
is not production approval or proof of publication. Direct upstream version tags
run protected-main checks and reusable CI, publish the immutable artifacts to
TestPyPI, verify them, and then wait for the owner's production approval. Never
retag or substitute a rebuilt payload during recovery.
