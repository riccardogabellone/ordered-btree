"""Release provenance, immutable handoff and index recovery; never upload anything."""

from __future__ import annotations

import hashlib
import importlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError

import pytest

ROOT = Path(__file__).resolve().parents[1]
WHEEL = "ordered_btree-0.1.0-py3-none-any.whl"
SDIST = "ordered_btree-0.1.0.tar.gz"
URLS = {
    "Repository": "https://github.com/riccardogabellone/ordered-btree",
    "Issues": "https://github.com/riccardogabellone/ordered-btree/issues",
    "Documentation": "https://github.com/riccardogabellone/ordered-btree/tree/main/docs",
    "Changelog": "https://github.com/riccardogabellone/ordered-btree/blob/main/CHANGELOG.md",
}


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(
        [
            "git",
            "-c",
            "user.name=Release Test",
            "-c",
            "user.email=test@example.invalid",
            "-c",
            "core.hooksPath=/dev/null",
            "-C",
            str(root),
            *args,
        ],
        text=True,
        encoding="utf-8",
        stderr=subprocess.PIPE,
    ).strip()


@pytest.fixture
def source(tmp_path: Path) -> Path:
    project = tmp_path / "source"
    project.mkdir()
    for name in ("pyproject.toml", "README.md", "LICENSE"):
        shutil.copy2(ROOT / name, project / name)
    shutil.copytree(
        ROOT / "src" / "ordered_btree",
        project / "src" / "ordered_btree",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    git(project, "init", "--initial-branch=main")
    git(project, "add", ".")
    git(project, "commit", "-m", "Initial source")
    git(project, "update-ref", "refs/remotes/origin/main", "HEAD")
    git(project, "tag", "-a", "v0.1.0", "-m", "Release")
    return project


@pytest.fixture
def pair(source: Path) -> Path:
    dist = source.parent / "dist"
    dist.mkdir()
    (dist / WHEEL).write_bytes(b"wheel")
    (dist / SDIST).write_bytes(b"sdist")
    return dist


def release() -> Any:
    return importlib.import_module("tools.release")


def manifest(source: Path, pair: Path) -> dict[str, Any]:
    return release().make_manifest(pair, source, git(source, "rev-parse", "HEAD"))


def index_payload(*, host: str = "files.pythonhosted.org") -> dict[str, Any]:
    return {
        "info": {"name": "ordered-btree", "version": "0.1.0", "project_urls": URLS},
        "urls": [
            {
                "filename": name,
                "digests": {"sha256": hashlib.sha256(content).hexdigest()},
                "url": f"https://{host}/packages/{name}",
                "size": len(content),
                "yanked": False,
            }
            for name, content in ((WHEEL, b"wheel"), (SDIST, b"sdist"))
        ],
    }


def test_provenance_cli_peels_annotated_tag_and_records_main_ancestry(source: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "release.py"),
            "provenance",
            "--project",
            str(source),
            "--ref",
            "refs/tags/v0.1.0",
            "--sha",
            git(source, "rev-parse", "refs/tags/v0.1.0"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"source_sha={git(source, 'rev-parse', 'HEAD')}" in result.stdout
    assert "version=0.1.0" in result.stdout


@pytest.mark.parametrize(
    "ref", ["refs/heads/v0.1.0", "v0.1.0", "refs/tags/v0.1.1", "refs/tags/v0.1.0a1"]
)
def test_provenance_rejects_nonexact_release_ref(source: Path, ref: str) -> None:
    with pytest.raises(ValueError, match="tag|version"):
        release().check_provenance(source, ref, git(source, "rev-parse", "HEAD"))


def test_provenance_rejects_side_branch_and_wrong_checkout(source: Path) -> None:
    base = git(source, "rev-parse", "HEAD")
    git(source, "switch", "-c", "side")
    (source / "side.txt").write_text("side branch\n")
    git(source, "add", ".")
    git(source, "commit", "-m", "Side branch")
    git(source, "tag", "-f", "v0.1.0")
    side = git(source, "rev-parse", "HEAD")
    with pytest.raises(ValueError, match="main"):
        release().check_provenance(source, "refs/tags/v0.1.0", side)
    git(source, "switch", "main")
    with pytest.raises(ValueError, match="checkout|HEAD"):
        release().check_provenance(source, "refs/tags/v0.1.0", side)
    with pytest.raises(ValueError, match="SHA|commit"):
        release().check_provenance(source, "refs/tags/v0.1.0", base)


def test_provenance_allows_tagged_ancestor_of_main(source: Path) -> None:
    sha = git(source, "rev-parse", "HEAD")
    (source / "later.txt").write_text("newer main\n")
    git(source, "add", ".")
    git(source, "commit", "-m", "Main advanced")
    git(source, "update-ref", "refs/remotes/origin/main", "HEAD")
    git(source, "checkout", "--detach", sha)
    assert release().check_provenance(source, "refs/tags/v0.1.0", sha)["source_sha"] == sha


def test_manifest_binds_exact_pair_and_source(source: Path, pair: Path) -> None:
    value = manifest(source, pair)
    assert value["source_sha"] == git(source, "rev-parse", "HEAD")
    assert value["files"] == {
        WHEEL: {"sha256": hashlib.sha256(b"wheel").hexdigest(), "size": 5},
        SDIST: {"sha256": hashlib.sha256(b"sdist").hexdigest(), "size": 5},
    }
    assert (
        value["source_sha256"]["pyproject.toml"]
        == hashlib.sha256((source / "pyproject.toml").read_bytes()).hexdigest()
    )
    release().check_manifest(pair, source, value, value["source_sha"])
    (pair / WHEEL).write_bytes(b"tampered")
    with pytest.raises(ValueError, match="manifest"):
        release().check_manifest(pair, source, value, value["source_sha"])


@pytest.mark.parametrize("extra", ["old.whl", "manifest.json", "nested"])
def test_manifest_rejects_any_upload_extra(source: Path, pair: Path, extra: str) -> None:
    (pair / extra).touch()
    with pytest.raises(ValueError, match="exact"):
        manifest(source, pair)


def test_manifest_rejects_dirty_or_wrong_source(source: Path, pair: Path) -> None:
    value = manifest(source, pair)
    with pytest.raises(ValueError, match="SHA|checkout"):
        release().make_manifest(pair, source, "0" * 40)
    (source / "README.md").write_text("uncommitted change\n")
    with pytest.raises(ValueError, match="dirty|source"):
        release().check_manifest(pair, source, value, value["source_sha"])


def test_manifest_file_handoff_rejects_changed_digest(source: Path, pair: Path) -> None:
    output = source.parent / "evidence" / "manifest.json"
    digest = release().write_manifest(output, manifest(source, pair))
    assert release().read_manifest(output, digest)["version"] == "0.1.0"
    assert (output.parent / "SHA256SUMS").read_text().count("\n") == 2
    output.write_text(output.read_text() + " ")
    with pytest.raises(ValueError, match="digest"):
        release().read_manifest(output, digest)
    with pytest.raises(FileExistsError):
        release().write_manifest(output, manifest(source, pair))


@pytest.mark.parametrize("present", [[], [WHEEL], [SDIST], [WHEEL, SDIST]])
def test_resume_stages_only_missing_originals(
    source: Path, pair: Path, monkeypatch: pytest.MonkeyPatch, present: list[str]
) -> None:
    tool = release()
    payload = index_payload()
    payload["urls"] = [item for item in payload["urls"] if item["filename"] in present]
    monkeypatch.setattr(tool, "fetch", lambda *_args: json.dumps(payload).encode())
    upload = source.parent / "upload"
    result = tool.stage_missing(pair, source, manifest(source, pair), "pypi", upload)
    expected = {WHEEL, SDIST} - set(present)
    assert {path.name for path in upload.iterdir()} == expected
    assert result["missing"] == sorted(expected)
    for path in upload.iterdir():
        assert path.read_bytes() == (pair / path.name).read_bytes()
    with pytest.raises(FileExistsError):
        tool.stage_missing(pair, source, manifest(source, pair), "pypi", upload)


@pytest.mark.parametrize(
    "problem", ["digest", "unknown", "duplicate", "yanked", "size", "version", "links", "url"]
)
def test_conflicting_index_fails_without_staging_or_retry(
    source: Path, pair: Path, monkeypatch: pytest.MonkeyPatch, problem: str
) -> None:
    tool = release()
    payload = index_payload()
    item = payload["urls"][0]
    if problem == "digest":
        item["digests"]["sha256"] = "0" * 64
    elif problem == "unknown":
        item["filename"] = "unexpected.whl"
    elif problem == "duplicate":
        payload["urls"].append(item)
    elif problem == "yanked":
        item["yanked"] = True
    elif problem == "size":
        item["size"] = 1
    elif problem == "version":
        payload["info"]["version"] = "0.1.1"
    elif problem == "links":
        payload["info"]["project_urls"] = {"Repository": "https://example.com/"}
    else:
        item["url"] = "https://files.pythonhosted.org.evil.invalid/file.whl"
    monkeypatch.setattr(tool, "fetch", lambda *_args: json.dumps(payload).encode())
    sleeps = []
    monkeypatch.setattr(tool.time, "sleep", sleeps.append)
    upload = source.parent / "upload"
    with pytest.raises(ValueError):
        tool.stage_missing(pair, source, manifest(source, pair), "pypi", upload)
    assert not upload.exists()
    assert not sleeps


def test_index_visibility_is_bounded_and_accepts_eventual_exact_pair(
    source: Path,
    pair: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool = release()
    values = [HTTPError("https://pypi.org/", 404, "not visible", None, None), index_payload()]
    requests = []
    sleeps = []

    def fetch(url: str, limit: int) -> bytes:
        requests.append((url, limit))
        result = values.pop(0)
        if isinstance(result, Exception):
            raise result
        return json.dumps(result).encode()

    monkeypatch.setattr(tool, "fetch", fetch)
    monkeypatch.setattr(tool.time, "sleep", sleeps.append)
    result = tool.wait_for_index("pypi", manifest(source, pair), source, complete=True, attempts=2)
    assert set(result) == {WHEEL, SDIST}
    assert requests[0][0] == "https://pypi.org/pypi/ordered-btree/0.1.0/json"
    assert len(requests) == 2 and sleeps == [5]
    monkeypatch.setattr(tool, "fetch", lambda *_args: (_ for _ in ()).throw(URLError("offline")))
    sleeps.clear()
    with pytest.raises(ValueError, match="visible|attempt"):
        tool.wait_for_index("pypi", manifest(source, pair), source, complete=True, attempts=3)
    assert sleeps == [5, 5]


def test_missing_index_version_can_stage_but_never_verify(
    source: Path,
    pair: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool = release()

    def missing(*_args: object) -> bytes:
        raise HTTPError("https://test.pypi.org/", 404, "absent", None, None)

    monkeypatch.setattr(tool, "fetch", missing)
    monkeypatch.setattr(tool.time, "sleep", lambda _: None)
    value = manifest(source, pair)
    upload = source.parent / "upload"
    assert tool.stage_missing(pair, source, value, "testpypi", upload)["missing"] == sorted(
        [WHEEL, SDIST]
    )
    with pytest.raises(ValueError, match="visible|attempt"):
        tool.wait_for_index("testpypi", value, source, complete=True, attempts=2)


@pytest.mark.parametrize(
    "url",
    [
        "http://pypi.org/pypi/x/json",
        "https://pypi.org.evil.invalid/x",
        "https://user:secret@pypi.org/x",
        "https://pypi.org:444/x",
        "https://pypi.org/x?token=secret",
    ],
)
def test_network_rejects_nonofficial_or_credentialed_urls_without_io(url: str) -> None:
    with pytest.raises(ValueError, match="official|URL"):
        release().fetch(url, 100)


def test_index_download_checks_actual_bytes_not_only_json(
    source: Path,
    pair: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool = release()
    monkeypatch.setattr(
        tool,
        "fetch",
        lambda url, _limit: (
            json.dumps(index_payload()).encode() if url.endswith("/json") else b"corrupted"
        ),
    )
    with pytest.raises(ValueError, match="download|digest"):
        tool.verify_index(pair, source, manifest(source, pair), "pypi", {"commands": []})


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv required for isolated installation")
def test_real_index_bytes_install_offline_without_source_or_dependencies(
    source: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool = release()
    dist = tmp_path / "built"
    subprocess.run(
        [
            "uv",
            "--no-config",
            "build",
            "--offline",
            "--no-sources",
            "--python",
            sys.executable,
            str(source),
            "--out-dir",
            str(dist),
            "--no-create-gitignore",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    )
    value = manifest(source, dist)
    payload = index_payload(host="test-files.pythonhosted.org")
    for item in payload["urls"]:
        item["digests"]["sha256"] = value["files"][item["filename"]]["sha256"]
        item["size"] = value["files"][item["filename"]]["size"]

    def fetch(url: str, limit: int) -> bytes:
        if url == "https://test.pypi.org/pypi/ordered-btree/0.1.0/json":
            return json.dumps(payload).encode()
        assert url.startswith("https://test-files.pythonhosted.org/packages/")
        data = (dist / url.rsplit("/", 1)[1]).read_bytes()
        assert len(data) <= limit
        return data

    monkeypatch.setattr(tool, "fetch", fetch)
    monkeypatch.setenv("GITHUB_TOKEN", "never-inherit-this-token")
    report: dict[str, Any] = {"commands": []}
    tool.verify_index(dist, source, value, "testpypi", report)
    assert report["status"] == "passed"
    assert report["installed"]["smoke"]["installed_distributions"] == ["ordered-btree"]
    assert report["installed"]["inspection"]["version"] == "0.1.0"
    assert report["installed"]["inspection"]["metadata"]["Project-URL"] == [
        f"{key}, {value}" for key, value in URLS.items()
    ]
    assert report["installed"]["smoke"]["isolated"] == 1
    assert not Path(report["installed"]["smoke"]["package_file"]).is_relative_to(source)
    install = report["commands"][1]["argv"]
    assert "--offline" in install and "--no-deps" in install and "--no-index" in install
