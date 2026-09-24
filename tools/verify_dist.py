"""Verify ONE fresh dist directory, independently rebuild its sdist, and smoke both wheels.

Usage: python tools/verify_dist.py PATH/TO/DIST [--project PATH/TO/CHECKOUT]
Requires exactly the current wheel and sdist; never deletes or overwrites inputs.
Extraction, build output, and installations use new directories outside the checkout.
This verifies local release artifacts, not arbitrary untrusted build backends.
"""

from __future__ import annotations

import argparse
import configparser
import csv
import json
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tools import wheel_smoke
elif __package__:
    from . import wheel_smoke
else:
    import wheel_smoke

ROOT_SOURCE_FILES = {
    "README.md",
    "CHANGELOG.md",
    "LICENSE",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "CODE_OF_CONDUCT.md",
    "pyproject.toml",
    "MANIFEST.in",
    "uv.lock",
    ".python-version",
}
SOURCE_PATTERNS = ("docs/*.md", "examples/*.py", "tests/*.py", "tools/*.py", "benchmarks/*.py")


def distribution_pair(directory: Path, project: Path) -> tuple[Path, Path]:
    """Reject missing artifacts, stale versions, subdirectories, and upload-glob extras."""
    stem = wheel_smoke.distribution_stem(project)
    expected = {f"{stem}-py3-none-any.whl", f"{stem}.tar.gz"}
    wheel_smoke.require(directory.is_dir(), f"not a dist directory: {directory}")
    entries = list(directory.iterdir())
    wheel_smoke.require(
        {path.name for path in entries} == expected,
        f"dist must contain exactly {sorted(expected)}; got {sorted(p.name for p in entries)}",
    )
    wheel_smoke.require(
        all(path.is_file() and not path.is_symlink() for path in entries),
        "dist artifacts must be regular files, not symlinks",
    )
    return directory / f"{stem}-py3-none-any.whl", directory / f"{stem}.tar.gz"


def sdist_source_files(project: Path) -> dict[str, bytes]:
    paths = [project / name for name in ROOT_SOURCE_FILES if (project / name).is_file()]
    paths.extend(project / "src" / name for name in wheel_smoke.RUNTIME_FILES)
    for pattern in SOURCE_PATTERNS:
        paths.extend(project.glob(pattern))
    result = {}
    for path in paths:
        name = path.relative_to(project).as_posix()
        # Notes/caches are not distributable just because their suffix matches.
        if (
            any(
                part.startswith(("AGENT", "CLAUDE", ".")) or part == "__pycache__"
                for part in Path(name).parts
            )
            and name != ".python-version"
        ):
            continue
        wheel_smoke.require(path.is_file() and not path.is_symlink(), f"unsafe source file: {name}")
        result[name] = path.read_bytes()
    return result


def validate_sdist(archive: tarfile.TarFile, project: Path) -> dict[str, bytes]:
    """Validate the same open tar that will be extracted, without writing any bytes."""
    stem = wheel_smoke.distribution_stem(project)
    source = sdist_source_files(project)
    egg = "src/ordered_btree.egg-info"
    generated = {"PKG-INFO", "setup.cfg"} | {
        f"{egg}/{name}"
        for name in ("PKG-INFO", "SOURCES.txt", "dependency_links.txt", "top_level.txt")
    }
    allowed = source.keys() | generated
    directories = {stem} | {
        f"{stem}/{parent}"
        for name in allowed
        for parent in PurePosixPath(name).parents
        if str(parent) != "."
    }
    members: dict[str, bytes] = {}
    seen: set[str] = set()
    entries = archive.getmembers()
    wheel_smoke.require(
        len(entries) <= 2000
        and sum(item.size for item in entries) <= wheel_smoke.MAX_UNPACKED_BYTES,
        "sdist exceeds verification size limit",
    )
    for item in entries:
        name = wheel_smoke.safe_member_name(item.name)
        wheel_smoke.require(name.casefold() not in seen, f"duplicate sdist member: {name}")
        seen.add(name.casefold())
        wheel_smoke.require(
            item.isdir() or item.isfile(), f"sdist member is not a regular file: {name}"
        )
        if item.isdir():
            wheel_smoke.require(name in directories, f"unexpected sdist directory: {name}")
            continue
        wheel_smoke.require(name.startswith(stem + "/"), f"unexpected sdist root: {name}")
        relative = name[len(stem) + 1 :]
        wheel_smoke.require(relative in allowed, f"unexpected sdist member: {relative}")
        stream = archive.extractfile(item)
        if stream is None:
            raise ValueError(f"unreadable sdist file: {name}")
        with stream:
            members[relative] = stream.read()
    required = source.keys() | {"PKG-INFO"}
    wheel_smoke.require(
        required <= members.keys(),
        f"sdist missing source files: {sorted(required - members.keys())}",
    )
    for name, content in source.items():
        wheel_smoke.require(members[name] == content, f"sdist differs from source: {name}")
    wheel_smoke.check_metadata(members["PKG-INFO"], project)
    if f"{egg}/PKG-INFO" in members:
        wheel_smoke.require(
            members[f"{egg}/PKG-INFO"] == members["PKG-INFO"], "conflicting sdist PKG-INFO"
        )
    if f"{egg}/top_level.txt" in members:
        wheel_smoke.require(
            members[f"{egg}/top_level.txt"].strip() == b"ordered_btree", "unexpected sdist package"
        )
    if f"{egg}/dependency_links.txt" in members:
        wheel_smoke.require(
            not members[f"{egg}/dependency_links.txt"].strip(), "sdist has dependency links"
        )
    if f"{egg}/SOURCES.txt" in members:
        for name in members[f"{egg}/SOURCES.txt"].decode("utf-8").splitlines():
            wheel_smoke.require(
                wheel_smoke.safe_member_name(name) in allowed,
                f"unexpected sdist SOURCES.txt entry: {name}",
            )
    if "setup.cfg" in members:
        config = configparser.ConfigParser(interpolation=None)
        config.read_string(members["setup.cfg"].decode("utf-8"))
        wheel_smoke.require(
            not config.defaults()
            and config.sections() == ["egg_info"]
            and dict(config["egg_info"]) == {"tag_build": "", "tag_date": "0"},
            "unexpected generated setup.cfg settings",
        )
    return members


def extract_sdist(sdist: Path, project: Path, destination: Path) -> Path:
    """Extract only after validation, into a new external directory with tar's data filter."""
    project = project.resolve(strict=True)
    destination = destination.resolve()
    wheel_smoke.require(not destination.exists(), "extraction destination already exists")
    wheel_smoke.require(
        not destination.is_relative_to(project)
        and not destination.is_relative_to(wheel_smoke.DEFAULT_PROJECT),
        "sdist extraction must be outside the checkout",
    )
    stem = wheel_smoke.distribution_stem(project)
    wheel_smoke.require(
        sdist.name == f"{stem}.tar.gz" and not sdist.is_symlink(), "unexpected sdist filename/type"
    )
    with tarfile.open(sdist, "r:gz") as archive:
        members = validate_sdist(archive, project)
        destination.mkdir(parents=True)
        archive.extractall(destination, filter="data")
    source = destination / stem
    for name, content in members.items():
        wheel_smoke.require(
            (source / name).read_bytes() == content, f"extracted bytes changed: {name}"
        )
    return source


def compare_wheels(original: dict[str, Any], rebuilt: dict[str, Any]) -> None:
    """Compare all uncompressed member bytes, including METADATA/WHEEL/RECORD.

    ZIP timestamps/compression may differ; no differences inside files are waived.
    """
    wheel_smoke.require(
        original["archive_members"] == rebuilt["archive_members"],
        "original and rebuilt wheel member lists differ",
    )
    first, second = original["member_sha256"], rebuilt["member_sha256"]
    differences = sorted(
        name for name in first.keys() | second.keys() if first.get(name) != second.get(name)
    )
    wheel_smoke.require(
        not differences, f"original and rebuilt wheel members differ: {differences}"
    )


def verify_dist(directory: Path, project: Path, report: dict[str, Any]) -> None:
    project = project.resolve(strict=True)
    wheel, sdist = distribution_pair(directory.resolve(strict=True), project)
    report["original"] = wheel_smoke.inspect_wheel(wheel, project)
    report["sdist"] = {"path": str(sdist), "sha256": wheel_smoke.sha256(sdist.read_bytes())}
    commands = report["commands"]
    with tempfile.TemporaryDirectory(prefix="ordered-btree-sdist-") as temporary:
        root = Path(temporary).resolve()
        extracted = extract_sdist(sdist, project, root / "source")
        output = root / "rebuilt"
        wheel_smoke.run_command(
            [
                "uv",
                "--no-config",
                "build",
                "--no-sources",
                "--no-python-downloads",
                "--python",
                sys.executable,
                "--wheel",
                str(extracted),
                "--out-dir",
                str(output),
                "--no-create-gitignore",
            ],
            root,
            commands,
        )
        expected = output / wheel.name
        wheel_smoke.require(
            list(output.iterdir()) == [expected], "rebuild produced unexpected output files"
        )
        rebuilt = wheel_smoke.inspect_wheel(expected, extracted)
        compare_wheels(report["original"], rebuilt)
        report["comparison"] = (
            "all wheel member bytes identical, including RECORD; ZIP container may differ"
        )
        report["original_smoke"] = wheel_smoke.smoke_wheel(wheel, project, commands)
        report["rebuilt_smoke"] = wheel_smoke.smoke_wheel(expected, extracted, commands)
    wheel_smoke.require(
        wheel_smoke.sha256(sdist.read_bytes()) == report["sdist"]["sha256"],
        "sdist changed during verification",
    )
    report["status"] = "passed"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dist", type=Path, help="one fresh directory, not a wildcard")
    parser.add_argument("--project", type=Path, default=wheel_smoke.DEFAULT_PROJECT)
    args = parser.parse_args()
    if sys.flags.optimize:
        parser.error("optimized Python (-O/-OO) is not supported")
    report: dict[str, Any] = {
        "status": "failed",
        "runtime": wheel_smoke.provenance(),
        "commands": [],
    }
    try:
        verify_dist(args.dist, args.project, report)
    except (
        OSError,
        ValueError,
        KeyError,
        csv.Error,
        configparser.Error,
        tarfile.TarError,
        zipfile.BadZipFile,
        subprocess.CalledProcessError,
    ) as error:
        report["error"] = str(error)
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
