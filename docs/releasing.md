# Build and release checklist

## Three distinct states

1. **Builds locally:** wheel and source archive can be produced and installed.
2. **Verified candidate:** identified source and artifact hashes passed the recorded
   test/runtime matrix and independent artifact checks, with limitations disclosed.
3. **Authorized for publication:** the owner separately approved the destination,
   public metadata and upload. Neither of the first two states implies this one.

The distribution name is `ordered-btree`, import `ordered_btree`, version
`0.1.0a1`, license MIT, author Riccardo Gabellone (no public email). The intended
matching GitHub repository has not been created. PyPI and TestPyPI had no listing
for this name when checked on 2026-09-23; that does not reserve it, establish
ownership or guarantee name eligibility.

Publication remains blocked by `Private :: Do Not Upload`,
`publication-approved = false`, and missing live repository metadata. The name
choice is confirmed (`name-confirmed = true`). Local Git commits do not authorize
remote creation, pushing, tags, release workflows or package uploads.

## Validate the intended source

Install uv 0.12.15 or newer. Keep uv.lock committed and use locked environments:

```bash
uv sync --locked
uv lock --check
uv run --locked pytest -q -m "not stress"
uv run --locked pytest -q -m stress
uv run --locked python tools/stress.py
uv run --locked coverage run -m pytest -q -m "not stress"
uv run --locked coverage report --fail-under=99
uv run --locked mypy
uv run --locked ruff check src examples tests tools benchmarks
uv run --locked ruff format --check src examples tests tools benchmarks
uv run --locked python examples/basic.py
uv run --locked python examples/records.py
uv run --locked python examples/synchronized.py
uv run --locked python benchmarks/benchmark.py
```

Run the declared Python 3.12/3.13/3.14 Linux/Windows matrix where available and
record unavailable entries explicitly. Test free-threaded builds separately;
this does not establish shared-instance thread safety. Hypothesis must be
installed/collected, not skipped. Do not use optimized Python for verification.

Use fresh, run-specific results directories. Retain exact argv, exit codes,
interpreter/build/platform/GIL state, tool versions, seeds, loaded-source hashes,
reports and failures. Hash the source being tested, including tests and tools.
A modified source tree needs fresh evidence. Do not overwrite previous logs.
See [validation](validation.md) for the actual run record, not just configured CI.

## Build and inspect fresh artifacts

Choose a new output directory for every attempt (including failed attempts).
Do not delete or mix previously generated artifacts into an upload wildcard.

```bash
uv build --no-create-gitignore --out-dir dist/candidate
uv run --locked twine check --strict dist/candidate/*
uv run --locked python tools/verify_dist.py dist/candidate
```

`verify_dist.py` requires exactly the candidate wheel and sdist. It verifies the
runtime file allowlist, package metadata, `py.typed`, zero `Requires-Dist`, RECORD
hashes and matching source bytes. It installs into an external temporary uv
virtual environment, proving the isolated import comes from the installed wheel.
It safely extracts the sdist outside the checkout, rebuilds using uv, compares
wheel contents and independently repeats the installation smoke.

The wheel contains only `ordered_btree` and distribution metadata. The sdist
contains public docs, tests, tools, examples, benchmark and uv configuration;
it excludes GitHub configuration, logs, caches, environments and agent notes.
uv is not a runtime dependency, and the standard build frontend remains supported:

```bash
uv run --locked python -m build --installer uv --outdir dist/frontend-check
uv run --locked twine check --strict dist/frontend-check/*
uv run --locked python tools/verify_dist.py dist/frontend-check
```

A successful artifact check is not legal review, proof of index ownership, or
publication approval. `pyproject.toml` is the only authoritative version source;
consumers use `importlib.metadata.version("ordered-btree")`.

## Source ZIP and evidence

After reviewing and committing the source, archive the committed tree, not the
entire working directory. Create an `artifacts/` directory first:

```bash
git archive --format=zip --prefix=ordered-btree/ --output=artifacts/ordered-btree-0.1.0a1-project.zip HEAD
```

This project ZIP contains repository files, including public docs and CI, but no
ignored files or Git internals. Deliver the wheel/sdist alongside it. Generate a
SHA256 manifest for the three artifacts and associate the source commit/file
hashes with the separately retained validation logs. Inspect the ZIP file list
before sharing it. Do not commit binaries, credentials, caches or raw evidence.

## Before making a repository public

Obtain explicit authorization to create/push the matching repository. Review
[CONTRIBUTING.md](../CONTRIBUTING.md), [SECURITY.md](../SECURITY.md) and the conduct
policy. Enable branch protection/status requirements, private vulnerability
reporting, available secret/dependency scanning and restricted Actions permissions.
These are remote settings: checked-in configuration does not enable them.

Only after the repository exists, add its actual Repository/Issues URLs to
`[project.urls]`. Replace relative README links with public, version-appropriate
URLs before publishing to an index, so the index-rendered README has working
links. Verify the display name, MIT notice, redistribution rights and all archive
contents; do not invent metadata or copy credentials into project files.

## Publish only with separate explicit authorization

Recheck name eligibility/ownership on the intended index immediately before the
release. Get explicit approval for TestPyPI and, separately, PyPI. Only then
remove the private classifier, set `publication-approved = true`, replace CI's
temporary **Require publication guard** step with the positive preflight check,
and rebuild/revalidate artifacts from those final metadata bytes:

```bash
uv run --locked python tools/check_release.py
```

This command never uploads. Until approval and live metadata exist it must exit
nonzero, even if every local test passes. Publish only the exact newly verified
artifacts, using separately configured trusted publishing or scoped credentials.
Never commit tokens. Verify installation from TestPyPI in another clean
environment before considering PyPI. No automatic publishing workflow is included.

## Official references

- [uv projects and lockfiles](https://docs.astral.sh/uv/guides/projects/)
- [uv development dependency groups](https://docs.astral.sh/uv/concepts/projects/dependencies/)
- [uv locking and syncing](https://docs.astral.sh/uv/concepts/projects/sync/)
- [uv GitHub Actions](https://docs.astral.sh/uv/guides/integration/github/)
- [PyPA metadata and licensing](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/)
- [TestPyPI](https://packaging.python.org/en/latest/guides/using-testpypi/)
- [Typed distributions](https://typing.python.org/en/latest/spec/distributing.html)
