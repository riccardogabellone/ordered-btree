"""Focused archive regressions; real uv installation is exercised without an index."""

from __future__ import annotations

import base64
import csv
import hashlib
import importlib
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

from tools import wheel_smoke

ROOT = Path(__file__).resolve().parents[1]
STEM = "ordered_btree-0.1.0a1"
INFO = f"{STEM}.dist-info"


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    package = root / "src" / "ordered_btree"
    package.mkdir(parents=True)
    (root / "pyproject.toml").write_text(
        '[project]\nname = "ordered-btree"\nversion = "0.1.0a1"\n'
        'requires-python = ">=3.12"\nlicense = "MIT"\nlicense-files = ["LICENSE"]\n'
        'authors = [{name = "Riccardo Gabellone"}]\ndependencies = []\n'
        'classifiers = ["Private :: Do Not Upload"]\nreadme = "README.md"\n',
        encoding="utf-8",
    )
    (root / "README.md").write_text("# Fixture\n", encoding="utf-8")
    (root / "LICENSE").write_text("MIT fixture license\n", encoding="utf-8")
    (root / "MANIFEST.in").write_text("include LICENSE\n", encoding="utf-8")
    (package / "__init__.py").write_text("from ._tree import BTree\n", encoding="utf-8")
    (package / "_tree.py").write_text("class BTree: pass\n", encoding="utf-8")
    (package / "py.typed").write_bytes(b"")
    return root


def wheel_members(project: Path) -> dict[str, bytes]:
    members = {
        f"ordered_btree/{name}": (project / "src" / "ordered_btree" / name).read_bytes()
        for name in ("__init__.py", "_tree.py", "py.typed")
    }
    members.update(
        {
            f"{INFO}/METADATA": (
                b"Metadata-Version: 2.4\nName: ordered-btree\nVersion: 0.1.0a1\n"
                b"Requires-Python: >=3.12\nLicense-Expression: MIT\nLicense-File: LICENSE\n"
                b"Author: Riccardo Gabellone\nClassifier: Private :: Do Not Upload\n"
                b"Description-Content-Type: text/markdown\n\n# Fixture\n"
            ),
            f"{INFO}/WHEEL": (
                b"Wheel-Version: 1.0\nGenerator: artifact-test\n"
                b"Root-Is-Purelib: true\nTag: py3-none-any\n"
            ),
            f"{INFO}/top_level.txt": b"ordered_btree\n",
            f"{INFO}/licenses/LICENSE": (project / "LICENSE").read_bytes(),
        }
    )
    return members


def write_wheel(path: Path, members: dict[str, bytes], *, record: bytes | None = None) -> Path:
    """Build an independent minimal wheel, including real RECORD digests."""
    rows = []
    for name, data in members.items():
        digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
        rows.append((name, f"sha256={digest}", str(len(data))))
    rows.append((f"{INFO}/RECORD", "", ""))
    output = io.StringIO(newline="")
    csv.writer(output, lineterminator="\n").writerows(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in members.items():
            archive.writestr(name, data)
        archive.writestr(f"{INFO}/RECORD", output.getvalue().encode() if record is None else record)
    return path


PUBLIC_URLS = {
    "Repository": "https://github.com/riccardogabellone/ordered-btree",
    "Issues": "https://github.com/riccardogabellone/ordered-btree/issues",
    "Documentation": "https://github.com/riccardogabellone/ordered-btree/tree/main/docs",
    "Changelog": "https://github.com/riccardogabellone/ordered-btree/blob/main/CHANGELOG.md",
}


@pytest.mark.parametrize("change", ["exact", "missing", "wrong", "duplicate", "unexpected"])
@pytest.mark.parametrize("archive_kind", ["wheel", "sdist"])
def test_public_project_urls_are_exact(project: Path, change: str, archive_kind: str) -> None:
    # Keep the private/alpha fixtures above independent of the live project metadata.
    config = project / "pyproject.toml"
    config.write_text(
        config.read_text(encoding="utf-8").replace(
            'classifiers = ["Private :: Do Not Upload"]', "classifiers = []"
        )
        + "\n[project.urls]\n"
        + "".join(f'{label} = "{url}"\n' for label, url in PUBLIC_URLS.items()),
        encoding="utf-8",
    )
    fields = [f"{label}, {url}" for label, url in PUBLIC_URLS.items()]
    if change == "missing":
        fields.pop()
    elif change == "wrong":
        fields[0] = "Repository, https://github.com/someone/another-project"
    elif change == "duplicate":
        fields.append(fields[0])
    elif change == "unexpected":
        fields.append("Homepage, https://example.com/")
    data = wheel_members(project)[f"{INFO}/METADATA"].replace(
        b"Classifier: Private :: Do Not Upload\n", b""
    )
    data = data.replace(
        b"\n\n", ("\n" + "".join(f"Project-URL: {field}\n" for field in fields) + "\n").encode(), 1
    )
    if archive_kind == "wheel":
        members = wheel_members(project)
        members[f"{INFO}/METADATA"] = data
        path = write_wheel(project.parent / f"{STEM}-py3-none-any.whl", members)

        def check() -> None:
            result = wheel_smoke.inspect_wheel(path, project)
            assert result["metadata"]["Project-URL"] == [
                f"{label}, {url}" for label, url in PUBLIC_URLS.items()
            ]
    else:
        from tools import verify_dist

        members = sdist_members(project)
        members["PKG-INFO"] = data
        path = write_sdist(project.parent / f"{STEM}.tar.gz", members)

        def check() -> None:
            with tarfile.open(path, "r:gz") as archive:
                verify_dist.validate_sdist(archive, project)

    if change == "exact":
        check()
    else:
        with pytest.raises(ValueError, match="Project-URL"):
            check()


def test_install_environment_contains_no_inherited_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for key in (
        "GITHUB_TOKEN",
        "GH_TOKEN",
        "ACTIONS_ID_TOKEN_REQUEST_TOKEN",
        "AWS_SECRET_ACCESS_KEY",
        "ARBITRARY_SERVICE_SECRET",
        "UV_INDEX",
        "PIP_INDEX_URL",
        "PYTHONPATH",
        "VIRTUAL_ENV",
        "HTTPS_PROXY",
    ):
        monkeypatch.setenv(key, "must-not-reach-clean-install")
    monkeypatch.setenv("PATH", "required-for-uv")
    env = wheel_smoke.clean_environment()
    sentinel_survived = "must-not-reach-clean-install" in env.values()
    assert not sentinel_survived, "inherited credentials reached the install environment"
    assert env["PATH"] == "required-for-uv"


def test_wheel_inspection_accepts_exact_package_and_checks_source(project: Path) -> None:
    wheel = write_wheel(project.parent / f"{STEM}-py3-none-any.whl", wheel_members(project))
    result = wheel_smoke.inspect_wheel(wheel, project)
    assert result["name"] == "ordered-btree"
    assert result["version"] == "0.1.0a1"
    assert result["runtime_sha256"]["ordered_btree/py.typed"] == hashlib.sha256(b"").hexdigest()
    (project / "src" / "ordered_btree" / "_tree.py").write_text("# changed\n", encoding="utf-8")
    with pytest.raises(ValueError, match="source"):
        wheel_smoke.inspect_wheel(wheel, project)


@pytest.mark.parametrize(
    "unexpected",
    [
        "other_package/__init__.py",
        "ordered_btree/extra.py",
        "rogue.dist-info/METADATA",
        f"{INFO}/entry_points.txt",
        "../outside.py",
        "ordered_btree/../outside.py",
        "ordered_btree\\outside.py",
        "/ordered_btree/outside.py",
        "C:/outside.py",
    ],
)
def test_wheel_rejects_unexpected_or_unsafe_member(project: Path, unexpected: str) -> None:
    members = wheel_members(project)
    members[unexpected] = b"unwanted\n"
    wheel = write_wheel(project.parent / f"{STEM}-py3-none-any.whl", members)
    with pytest.raises(ValueError):
        wheel_smoke.inspect_wheel(wheel, project)


@pytest.mark.parametrize("missing", ["ordered_btree/py.typed", f"{INFO}/licenses/LICENSE"])
def test_wheel_rejects_missing_required_file(project: Path, missing: str) -> None:
    members = wheel_members(project)
    del members[missing]
    wheel = write_wheel(project.parent / f"{STEM}-py3-none-any.whl", members)
    with pytest.raises(ValueError):
        wheel_smoke.inspect_wheel(wheel, project)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        (b"Version: 0.1.0a1", b"Version: 0.1.0a2"),
        (b"Name: ordered-btree", b"Name: different-btree"),
        (b"Requires-Python: >=3.12", b"Requires-Python: >=3.14"),
        (b"License-Expression: MIT", b"License-Expression: BSD-3-Clause"),
        (b"Author: Riccardo Gabellone", b"Author: Someone Else"),
        (
            b"Author: Riccardo Gabellone",
            b"Author: Riccardo Gabellone\nAuthor-email: invented@example.com",
        ),
        (b"Classifier: Private :: Do Not Upload", b"Classifier: Programming Language :: Python"),
        (b"Requires-Python: >=3.12", b"Requires-Python: >=3.12\nRequires-Dist: requests"),
        (
            b"Requires-Python: >=3.12",
            b'Requires-Python: >=3.12\nRequires-Dist: pytest; extra == "dev"',
        ),
        (b"Version: 0.1.0a1", b"Version: 0.1.0a1\nVersion: 0.1.0a2"),
    ],
)
def test_wheel_rejects_wrong_metadata(project: Path, old: bytes, new: bytes) -> None:
    members = wheel_members(project)
    members[f"{INFO}/METADATA"] = members[f"{INFO}/METADATA"].replace(old, new)
    wheel = write_wheel(project.parent / f"{STEM}-py3-none-any.whl", members)
    with pytest.raises(ValueError):
        wheel_smoke.inspect_wheel(wheel, project)


@pytest.mark.parametrize("record", [b"", b"missing.py,sha256=wrong,123\n", b"malformed\n"])
def test_wheel_rejects_invalid_record(project: Path, record: bytes) -> None:
    wheel = write_wheel(
        project.parent / f"{STEM}-py3-none-any.whl", wheel_members(project), record=record
    )
    with pytest.raises(ValueError, match="RECORD"):
        wheel_smoke.inspect_wheel(wheel, project)


def test_wheel_rejects_incorrect_record_hash(project: Path) -> None:
    path = project.parent / f"{STEM}-py3-none-any.whl"
    members = wheel_members(project)
    write_wheel(path, members)
    with zipfile.ZipFile(path) as archive:
        record = archive.read(f"{INFO}/RECORD")
    record = record.replace(b"sha256=", b"sha256=bad", 1)
    write_wheel(path, members, record=record)
    with pytest.raises(ValueError, match="RECORD"):
        wheel_smoke.inspect_wheel(path, project)


def test_wheel_rejects_symlink(project: Path) -> None:
    path = write_wheel(project.parent / f"{STEM}-py3-none-any.whl", wheel_members(project))
    with zipfile.ZipFile(path) as archive:
        entries = [(item, archive.read(item)) for item in archive.infolist()]
    with zipfile.ZipFile(path, "w") as archive:
        for item, content in entries:
            if item.filename == "ordered_btree/_tree.py":
                item.create_system = 3
                item.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(item, content)
    with pytest.raises(ValueError, match="regular|symlink"):
        wheel_smoke.inspect_wheel(path, project)


def test_wheel_rejects_duplicate_members(project: Path) -> None:
    path = write_wheel(project.parent / f"{STEM}-py3-none-any.whl", wheel_members(project))
    with zipfile.ZipFile(path, "a") as archive, pytest.warns(UserWarning, match="Duplicate name"):
        archive.writestr("ordered_btree/py.typed", b"")
    with pytest.raises(ValueError, match="duplicate"):
        wheel_smoke.inspect_wheel(path, project)


def test_optimized_cli_fails_before_inspection_or_install(tmp_path: Path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-O",
            str(ROOT / "tools" / "wheel_smoke.py"),
            str(tmp_path / "missing.whl"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode != 0
    assert "optimized Python" in completed.stdout + completed.stderr


def sdist_members(project: Path) -> dict[str, bytes]:
    members = {
        path.relative_to(project).as_posix(): path.read_bytes()
        for path in project.rglob("*")
        if path.is_file()
    }
    members["PKG-INFO"] = wheel_members(project)[f"{INFO}/METADATA"]
    members["setup.cfg"] = b"[egg_info]\ntag_build = \ntag_date = 0\n\n"
    return members


def write_sdist(
    path: Path, members: dict[str, bytes], *, unsafe: tarfile.TarInfo | None = None
) -> Path:
    with tarfile.open(path, "w:gz") as archive:
        for name, content in members.items():
            info = tarfile.TarInfo(f"{STEM}/{name}")
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
        if unsafe is not None:
            archive.addfile(unsafe)
    return path


def test_sdist_safe_extraction_never_overwrites_existing_directory(project: Path) -> None:
    verify_dist = importlib.import_module("tools.verify_dist")
    archive = write_sdist(project.parent / f"{STEM}.tar.gz", sdist_members(project))
    destination = project.parent / "extracted"
    source = verify_dist.extract_sdist(archive, project, destination)
    assert (source / "src" / "ordered_btree" / "py.typed").is_file()
    with pytest.raises(ValueError, match="exist"):
        verify_dist.extract_sdist(archive, project, destination)


@pytest.mark.parametrize(
    "unexpected",
    [
        "../outside",
        "/absolute",
        "scratch/unintended.py",
        "AGENTS.md",
        ".env",
        "src/ordered_btree/__pycache__/bad.pyc",
        "results/token.json",
    ],
)
def test_sdist_rejects_unsafe_or_unintended_file(project: Path, unexpected: str) -> None:
    verify_dist = importlib.import_module("tools.verify_dist")
    members = sdist_members(project)
    members[unexpected] = b"should not escape\n"
    archive = write_sdist(project.parent / f"{STEM}.tar.gz", members)
    destination = project.parent / "extracted"
    with pytest.raises(ValueError):
        verify_dist.extract_sdist(archive, project, destination)
    assert not destination.exists()
    assert not (project.parent / "outside").exists()


@pytest.mark.parametrize("kind", [tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.FIFOTYPE])
def test_sdist_rejects_links_and_special_files(project: Path, kind: bytes) -> None:
    verify_dist = importlib.import_module("tools.verify_dist")
    info = tarfile.TarInfo(f"{STEM}/link")
    info.type = kind
    info.linkname = "../../outside"
    archive = write_sdist(project.parent / f"{STEM}.tar.gz", sdist_members(project), unsafe=info)
    with pytest.raises(ValueError):
        verify_dist.extract_sdist(archive, project, project.parent / "extracted")


def test_dist_directory_requires_exact_current_pair(project: Path) -> None:
    verify_dist = importlib.import_module("tools.verify_dist")
    dist = project.parent / "dist"
    dist.mkdir()
    wheel = dist / f"{STEM}-py3-none-any.whl"
    sdist = dist / f"{STEM}.tar.gz"
    wheel.touch()
    sdist.touch()
    assert verify_dist.distribution_pair(dist, project) == (wheel, sdist)
    (dist / "old.whl").touch()
    with pytest.raises(ValueError, match="exact|unexpected|stale"):
        verify_dist.distribution_pair(dist, project)


def test_rebuild_comparison_rejects_changed_directory_members(project: Path) -> None:
    verify_dist = importlib.import_module("tools.verify_dist")
    members = wheel_members(project)
    original = write_wheel(project.parent / "original" / f"{STEM}-py3-none-any.whl", members)
    rebuilt = write_wheel(project.parent / "rebuilt" / f"{STEM}-py3-none-any.whl", members)
    with zipfile.ZipFile(original, "a") as archive:
        archive.writestr("ordered_btree/", b"")
    with pytest.raises(ValueError, match="differ"):
        verify_dist.compare_wheels(
            wheel_smoke.inspect_wheel(original, project),
            wheel_smoke.inspect_wheel(rebuilt, project),
        )


def test_rebuild_comparison_rejects_changed_metadata(project: Path) -> None:
    verify_dist = importlib.import_module("tools.verify_dist")
    members = wheel_members(project)
    original = write_wheel(project.parent / "original" / f"{STEM}-py3-none-any.whl", members)
    members[f"{INFO}/WHEEL"] = members[f"{INFO}/WHEEL"].replace(
        b"artifact-test", b"another-backend"
    )
    rebuilt = write_wheel(project.parent / "rebuilt" / f"{STEM}-py3-none-any.whl", members)
    with pytest.raises(ValueError, match="differ"):
        verify_dist.compare_wheels(
            wheel_smoke.inspect_wheel(original, project),
            wheel_smoke.inspect_wheel(rebuilt, project),
        )


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv CLI is required for isolated install")
def test_real_wheel_import_is_isolated_from_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "real-source"
    shutil.copytree(
        ROOT / "src" / "ordered_btree",
        project / "src" / "ordered_btree",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    for name in ("pyproject.toml", "README.md", "LICENSE"):
        shutil.copy2(ROOT / name, project / name)
    dist = tmp_path / "built"
    subprocess.run(
        [
            "uv",
            "--no-config",
            "build",
            "--offline",
            "--no-sources",
            "--no-python-downloads",
            "--python",
            sys.executable,
            "--wheel",
            str(project),
            "--out-dir",
            str(dist),
            "--no-create-gitignore",
        ],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )
    shadow = tmp_path / "shadow"
    shadow.mkdir()
    (shadow / "ordered_btree.py").write_text(
        'raise RuntimeError("SOURCE IMPORTED")\n', encoding="utf-8"
    )
    monkeypatch.chdir(shadow)
    monkeypatch.setenv("PYTHONPATH", str(shadow))
    monkeypatch.setenv("UV_PROJECT", str(shadow))
    monkeypatch.setenv("UV_SYSTEM_PYTHON", "true")
    (wheel,) = dist.glob("*.whl")
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "wheel_smoke.py"),
            str(wheel),
            "--project",
            str(project),
        ],
        cwd=shadow,
        env=os.environ.copy(),
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    report = json.loads(completed.stdout)
    assert report["status"] == "passed"
    installed = report["smoke"]
    assert installed["isolated"] == 1
    assert installed["installed_distributions"] == ["ordered-btree"]
    assert Path(installed["package_file"]).is_relative_to(Path(installed["venv"]))
    assert not Path(installed["package_file"]).is_relative_to(project)
    assert not Path(installed["package_file"]).is_relative_to(shadow)
