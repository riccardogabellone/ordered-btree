# Build and release checklist

## Release identity and approval

The initial public version is **0.1.0**, distribution `ordered-btree`, import
`ordered_btree`, MIT, author Riccardo Gabellone (name only). The repository is
https://github.com/riccardogabellone/ordered-btree. This is a pre-1.0 API, not a
claim of 1.0 maturity. `pyproject.toml` is the version authority; consumers use
`importlib.metadata.version("ordered-btree")`.

Public metadata and TestPyPI preparation are approved. The **pypi environment
requires the owner's explicit production approval after TestPyPI verification**.
Local checks, configured workflows and pending Trusted Publishers do not prove
that publication happened. Use the actual Actions run, index files and GitHub
release to establish completion. Dated local results live in
[validation](validation.md), separate from future remote results.

## Required remote controls

Before tagging, the maintainer verifies the live settings, not just these files:

- Protected `main`: PR required, branch up to date, conversations resolved,
  linear history, exact `CI required` check from GitHub Actions, no bypass or
  force pushes/deletion. Zero additional mandatory reviewers supports the solo
  maintainer; only the owner/trusted collaborators can merge.
- Protect `v*` tags against update/deletion. Do not move or recreate a release tag.
- Both Trusted Publishers bind `riccardogabellone/ordered-btree`, **release.yml**
  and the matching **testpypi** / **pypi** environment. No package API tokens.
- Environments accept only `v*` tags. Production requires the owner as reviewer,
  permits that owner to approve their own initiated deployment, and disallows
  administrator bypass. Blocking self-review would deadlock the sole maintainer.
- Actions default to read-only, cannot approve PRs, and require approval for
  outside-fork workflows. Security/reporting controls are checked separately.

The repository homepage is set to the live PyPI project URL by the owner **after
production verification**. Updating it needs repository administration rights;
the release job deliberately has only `contents: write`, not an administrator token.

## Validate the intended source

Use uv 0.12.15 or newer and committed `uv.lock`. Do not silently upgrade tools.
The separately pinned setuptools 84.0.0 backend makes independent rebuilds use
the same backend. Changing its pin requires repeating artifact verification.

```bash
uv sync --locked
uv lock --check
uv run --locked pytest -q -m "not stress" --hypothesis-seed=12983
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
uv run --locked python tools/check_release.py
```

CI keeps eight Windows/Ubuntu configurations: Python 3.12, 3.13, 3.14 with the GIL,
and free-threaded 3.14. Hypothesis is required, never silently skipped. Bootstrap
ordinary 3.14 before selecting `3.14+gil`; assert the actual build/GIL state.
No verification under `-O` or `PYTHONOPTIMIZE`. Run performance measurements for
runtime/performance changes, not as a claim about the packaging pipeline.

CI also checks **both** workflows with checksum-pinned actionlint 1.7.12, so a
release-only syntax error cannot bypass the PR gate. All shell commands use block
scalars to avoid YAML interpretation of embedded Python such as `lambda: True`.

Use fresh evidence destinations. Record argv, exit status, interpreter/GIL/platform,
tool versions, source hashes and actually imported files. Preserve failures and
old evidence. A modified source tree needs fresh verification.

## Build and inspect fresh artifacts

Choose a new directory for every local attempt:

```bash
uv build --no-create-gitignore --out-dir dist/candidate
uv run --locked twine check --strict dist/candidate/*
uv run --locked python tools/verify_dist.py dist/candidate
```

`verify_dist.py` requires exactly one current wheel and sdist, verifies runtime
membership, metadata (including exact Project-URL multiplicity), `py.typed`,
zero dependencies, RECORD and source bytes. It installs the wheel in a fresh
external uv environment using `--offline --no-index --no-deps --no-build`, then
runs Python with `-I`. The probe verifies the imported distribution, version,
metadata and installed hashes. Only OS environment plumbing is inherited; tokens,
proxy credentials and installer/Python overrides are excluded. The sdist is
independently extracted/rebuilt and its wheel contents compared and installed.
That verification rebuild is **never** a publication payload.

The wheel contains only runtime files and metadata; the sdist also contains
public docs/tests/tools/examples and uv configuration, not `.github`, environments,
logs or agent notes. The standard PEP 517 frontend remains supported:

```bash
uv run --locked python -m build --installer uv --outdir dist/frontend-check
uv run --locked twine check --strict dist/frontend-check/*
uv run --locked python tools/verify_dist.py dist/frontend-check
```

A project ZIP, if needed, comes only from the reviewed committed Git tree:

```bash
git archive --format=zip --prefix=ordered-btree/ --output=artifacts/ordered-btree-0.1.0-project.zip HEAD
```

Create the output directory first. Inspect its membership and record its SHA256;
never ZIP the entire working directory.

## CI-to-release handoff

1. Branch pushes, PRs and manual CI run the matrix and quality checks. The
   `CI required` aggregate fails closed if any required job failed, was cancelled,
   or was skipped. Check the emitted check name before requiring it remotely.
2. Only a direct upstream `v*` tag push starts `release.yml`. It validates exact
   `v<project.version>`, peels annotated tags, requires full history, and proves
   the tagged commit is an ancestor of `origin/main`. Fork/PR and
   `pull_request_target`/`workflow_run` publishing paths do not exist.
3. Reusable CI checks out that exact peeled commit. It is the **sole** producer of
   the publication wheel/sdist. A manifest binds their filenames/sizes/SHA256s and
   tracked source-file hashes to the source commit. SHA256SUMS contains only the
   two distributions. Reports and manifest are separate from the flat payload.
4. Upload-artifact returns immutable numeric distribution/evidence identities.
   Reusable workflow outputs carry those IDs, the manifest digest and source SHA.
   A separate read-only CI job downloads by ID and checks flat layout and hashes;
   the required aggregate includes this handoff check.
5. The direct Ubuntu `publish-testpypi` job downloads those IDs, validates the
   manifest and stages missing originals. Only the two direct publishing jobs
   have `id-token: write`; neither installs development dependencies nor builds.
   The full-SHA official PyPA action uses OIDC and Sigstore attestations.
6. A separate read-only job checks TestPyPI's official version JSON, both file
   hashes and actual downloaded bytes, then performs the token-free installed
   wheel probe. **Only after that succeeds** can production request approval.
7. After the owner approves `pypi`, its publishing job stages the same original
   bytes. A read-only production job verifies hashes, install/version and the exact
   GitHub metadata backlinks. The final narrow `contents: write` job rechecks and
   attaches those retained distributions, manifest and SHA256SUMS to the GitHub
   release, whose notes link to the verified live PyPI version.

Release operations are serialized and never cancelled by a newer release. The
reusable CI concurrency prefix is distinct from the caller's prefix. Artifacts
are retained for 90 days; preserve originals externally before expiration if a
release needs a longer recovery window. GitHub artifacts are not permanent storage.

## Partial publication and recovery

Prefer **Re-run failed jobs** on the same tag workflow run. Never push another
copy of the tag, use `skip-existing`, upload a wildcard from a local build, or
rebuild a recovery payload. Re-running all jobs reuses the original immutable
artifact IDs; it does not rebuild. Missing, partial or expired original artifact
pairs on a release rerun cause a hard stop, including a failed first attempt that
never retained a complete pair. Investigate before taking any new release action.

Each index staging check accepts only the expected filenames with exact original
SHA256s and sizes. Duplicate, unknown, yanked or conflicting files fail immediately.
Only missing original files are copied into a **new** upload directory. If both
are already present, upload is skipped but read-only verification still runs.
A stale partial index response may cause an upload conflict; that fails safely,
then another same-run retry can observe the files. No mismatched file is silently
accepted. Index absence does not reserve a name or grant ownership.

Visibility checks make at most 12 attempts, with five-second delays and 30-second
network timeouts. Missing files/404 and transient 429/5xx/network failures can be
retried; invalid metadata, unsafe URLs and hash conflicts are not retried.
Only official HTTPS JSON/file hosts and credential-free URLs are accepted.
Job timeouts bound the complete verification, including installation. Persistent
outages stop the workflow without undoing completed uploads.

If final GitHub release creation was interrupted or the release already exists,
inspect the release and exact asset digests before any manual repair; the workflow
never clobbers existing release assets. Do not interpret a failed finalization as
an unpublished PyPI version. Retain stage reports and disclose what completed.

## Official references

- [uv projects and locking](https://docs.astral.sh/uv/guides/projects/)
- [uv GitHub Actions](https://docs.astral.sh/uv/guides/integration/github/)
- [PyPA metadata](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/)
- [Trusted Publishing](https://docs.pypi.org/trusted-publishers/using-a-publisher/)
- [Official PyPA publishing action](https://github.com/pypa/gh-action-pypi-publish)
- [PyPI JSON API](https://docs.pypi.org/api/json/)
- [GitHub workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax)
- [actionlint](https://github.com/rhysd/actionlint)
