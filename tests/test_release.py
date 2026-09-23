"""Publication checks must fail closed, independently of a successful build."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CONFIG = """\
[project]
name = "ordered-btree"
version = "0.1.0a1"
license = "MIT"
license-files = ["LICENSE"]
authors = [{name = "Example Maintainer"}]
classifiers = []
[project.urls]
Repository = "https://github.com/example/ordered-btree"
[tool.ordered-btree.release]
name-confirmed = true
publication-approved = true
"""


def preflight(tmp_path: Path, config: str, *flags: str) -> subprocess.CompletedProcess[str]:
    tool = tmp_path / "tools" / "check_release.py"
    tool.parent.mkdir()
    tool.write_bytes((ROOT / "tools" / "check_release.py").read_bytes())
    (tmp_path / "pyproject.toml").write_text(config, encoding="utf-8")
    (tmp_path / "LICENSE").write_text("Fixture license text\n", encoding="utf-8")
    return subprocess.run(
        [sys.executable, *flags, str(tool)],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )


@pytest.mark.parametrize("flags", [(), ("-O",), ("-OO",)])
def test_complete_metadata_passes_without_upload(tmp_path: Path, flags: tuple[str, ...]) -> None:
    result = preflight(tmp_path, CONFIG, *flags)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "separate" in result.stdout


@pytest.mark.parametrize(
    ("old", "new", "reason"),
    [
        ("classifiers = []", 'classifiers = ["Private :: Do Not Upload"]', "Private"),
        ("name-confirmed = true", "name-confirmed = false", "name"),
        ("publication-approved = true", "publication-approved = false", "publication"),
        ("publication-approved = true", "", "publication"),
        ('license = "MIT"', 'license = " "', "license"),
        ('license-files = ["LICENSE"]', 'license-files = ["missing*"]', "license"),
        ('license-files = ["LICENSE"]', 'license-files = ["tools"]', "license"),
        ('authors = [{name = "Example Maintainer"}]', "authors = [{}]", "author"),
        ('authors = [{name = "Example Maintainer"}]', 'authors = [{name = " "}]', "author"),
        (
            'Repository = "https://github.com/example/ordered-btree"',
            'Repository = "not-a-url"',
            "Repository",
        ),
        (
            'Repository = "https://github.com/example/ordered-btree"',
            'Repository = "https://user:secret@github.com/example/repo"',
            "Repository",
        ),
    ],
)
def test_incomplete_or_invalid_metadata_is_blocked(
    tmp_path: Path, old: str, new: str, reason: str
) -> None:
    result = preflight(tmp_path, CONFIG.replace(old, new))
    assert result.returncode == 1, result.stdout + result.stderr
    assert reason.lower() in result.stdout.lower()


def test_license_glob_cannot_escape_project(tmp_path: Path) -> None:
    (tmp_path / "outside-license").write_text("Not part of the project", encoding="utf-8")
    project = tmp_path / "project"
    project.mkdir()
    result = preflight(project, CONFIG.replace('["LICENSE"]', '["../outside-license"]'))
    assert result.returncode == 1, result.stdout + result.stderr
    assert "license" in result.stdout.lower()
