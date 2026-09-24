"""Verify and smoke ONE wheel against --project (default: this checkout).

Uses only the standard library and uv. No publishing or writes to the project;
stdout is a JSON provenance report, including failed subprocesses. Run without -O.
"""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import io
import json
import os
import platform
import re
import stat
import subprocess
import sys
import tempfile
import tomllib
import zipfile
from email import policy
from email.parser import BytesParser
from email.utils import formataddr
from pathlib import Path, PurePosixPath
from typing import Any

DEFAULT_PROJECT = Path(__file__).resolve().parents[1]
RUNTIME_FILES = frozenset(
    {
        "ordered_btree/__init__.py",
        "ordered_btree/_tree.py",
        "ordered_btree/py.typed",
    }
)
MAX_UNPACKED_BYTES = 32 * 1024 * 1024


def require(condition: object, message: str) -> None:
    """Unlike assert, verification must never disappear under optimized Python."""
    if not condition:
        raise ValueError(message)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_member_name(name: str) -> str:
    """Reject paths ambiguous on either Windows or POSIX, before extraction."""
    parts = name.removesuffix("/").split("/")
    require(
        name
        and not any(char in name for char in "\\:")
        and not any(ord(char) < 32 for char in name)
        and all(part not in {"", ".", ".."} and not part.endswith((".", " ")) for part in parts),
        f"unsafe archive member: {name!r}",
    )
    return "/".join(parts)


def project_metadata(project: Path) -> dict[str, Any]:
    with (project / "pyproject.toml").open("rb") as stream:
        metadata: dict[str, Any] = tomllib.load(stream)["project"]
    require(metadata["name"] == "ordered-btree", "expected the ordered-btree project")
    require(re.fullmatch(r"[0-9][A-Za-z0-9.!+]*", metadata["version"]), "unsafe project version")
    require(not metadata.get("dependencies"), "project must have no runtime dependencies")
    require(
        not metadata.get("optional-dependencies"), "development tools belong in dependency groups"
    )
    require(isinstance(metadata.get("license"), str), "project needs an SPDX license expression")
    require(
        metadata.get("license-files") == ["LICENSE"], "expected project license-files = ['LICENSE']"
    )
    return metadata


def distribution_stem(project: Path) -> str:
    metadata = project_metadata(project)
    return f"{re.sub(r'[-_.]+', '_', metadata['name'])}-{metadata['version']}"


def metadata_expectations(project: Path) -> dict[str, list[str]]:
    metadata = project_metadata(project)
    expected = {
        "Name": [metadata["name"]],
        "Version": [metadata["version"]],
        "Requires-Python": [metadata["requires-python"]],
        "License-Expression": [metadata["license"]],
        "License-File": metadata["license-files"],
        "Classifier": metadata.get("classifiers", []),
        "Requires-Dist": [],
        "Provides-Extra": [],
        "Project-URL": [f"{label}, {url}" for label, url in metadata.get("urls", {}).items()],
    }
    for role in ("Author", "Maintainer"):
        people = metadata.get(f"{role.lower()}s", [])
        names = [person["name"] for person in people if "email" not in person]
        emails = [
            formataddr((person.get("name", ""), person["email"]))
            for person in people
            if "email" in person
        ]
        expected[role] = [", ".join(names)] if names else []
        expected[f"{role}-email"] = [", ".join(emails)] if emails else []
    return expected


def check_metadata(data: bytes, project: Path) -> dict[str, list[str]]:
    metadata = BytesParser(policy=policy.default).parsebytes(data)
    require(not metadata.defects, f"malformed METADATA: {metadata.defects}")
    expected = metadata_expectations(project)
    for field, values in expected.items():
        actual = metadata.get_all(field, [])
        require(sorted(actual) == sorted(values), f"METADATA {field}: {actual!r} != {values!r}")
    return expected


def check_record(members: dict[str, bytes], record_name: str) -> None:
    rows = list(csv.reader(io.StringIO(members[record_name].decode("utf-8")), strict=True))
    recorded: set[str] = set()
    for row in rows:
        require(len(row) == 3, f"malformed RECORD row: {row!r}")
        name, digest, size = row
        require(
            name in members and name not in recorded, f"invalid/duplicate RECORD path: {name!r}"
        )
        recorded.add(name)
        if name == record_name:
            require(not digest and not size, "RECORD self-entry must have empty hash and size")
            continue
        algorithm, separator, value = digest.partition("=")
        require(
            separator and algorithm in {"sha256", "sha384", "sha512"}, f"unsafe RECORD hash: {name}"
        )
        actual = base64.urlsafe_b64encode(hashlib.new(algorithm, members[name]).digest()).rstrip(
            b"="
        )
        require(value == actual.decode("ascii"), f"RECORD hash mismatch: {name}")
        require(size == str(len(members[name])), f"RECORD size mismatch: {name}")
    require(recorded == set(members), "RECORD must list every file exactly once")


def inspect_wheel(wheel: Path, project: Path) -> dict[str, Any]:
    """Validate archive membership, metadata, RECORD, and exact runtime source bytes."""
    project = project.resolve(strict=True)
    stem = distribution_stem(project)
    require(wheel.name == f"{stem}-py3-none-any.whl", f"unexpected wheel filename: {wheel.name}")
    require(not wheel.is_symlink(), "wheel must not be a symlink")
    info = f"{stem}.dist-info"
    required = RUNTIME_FILES | {
        f"{info}/{name}"
        for name in (
            "METADATA",
            "WHEEL",
            "RECORD",
            "licenses/LICENSE",
        )
    }
    allowed = required | {f"{info}/top_level.txt"}
    directories = {
        str(parent)
        for name in allowed
        for parent in PurePosixPath(name).parents
        if str(parent) != "."
    }
    members: dict[str, bytes] = {}
    seen: set[str] = set()
    with zipfile.ZipFile(wheel) as archive:
        entries = archive.infolist()
        require(
            len(entries) <= 1000 and sum(item.file_size for item in entries) <= MAX_UNPACKED_BYTES,
            "wheel exceeds verification size limit",
        )
        for item in entries:
            name = safe_member_name(item.orig_filename)
            require(name.casefold() not in seen, f"duplicate wheel member: {name}")
            seen.add(name.casefold())
            mode = stat.S_IFMT(item.external_attr >> 16)
            require(
                mode in (0, stat.S_IFDIR if item.is_dir() else stat.S_IFREG),
                f"wheel member is not a regular file/directory (symlink?): {name}",
            )
            if item.is_dir():
                require(name in directories, f"unexpected wheel directory: {name}")
            else:
                require(name in allowed, f"unexpected wheel member: {name}")
                members[name] = archive.read(item)
    require(
        required <= members.keys(),
        f"wheel missing required files: {sorted(required - members.keys())}",
    )
    expected = check_metadata(members[f"{info}/METADATA"], project)
    wheel_metadata = BytesParser(policy=policy.default).parsebytes(members[f"{info}/WHEEL"])
    for field, value in (
        ("Wheel-Version", "1.0"),
        ("Root-Is-Purelib", "true"),
        ("Tag", "py3-none-any"),
    ):
        require(wheel_metadata.get_all(field) == [value], f"unexpected WHEEL {field}")
    if f"{info}/top_level.txt" in members:
        require(
            members[f"{info}/top_level.txt"].strip() == b"ordered_btree",
            "unexpected top-level package",
        )
    check_record(members, f"{info}/RECORD")
    for name in RUNTIME_FILES:
        source = project / "src" / name
        require(
            source.is_file() and not source.is_symlink(), f"missing/unsafe source file: {source}"
        )
        require(members[name] == source.read_bytes(), f"wheel differs from source: {name}")
    require(
        members[f"{info}/licenses/LICENSE"] == (project / "LICENSE").read_bytes(),
        "wheel license differs from source LICENSE",
    )
    return {
        "path": str(wheel.resolve()),
        "sha256": sha256(wheel.read_bytes()),
        "name": expected["Name"][0],
        "version": expected["Version"][0],
        "metadata": expected,
        "archive_members": sorted(item.filename for item in entries),
        "member_sha256": {name: sha256(data) for name, data in sorted(members.items())},
        "runtime_sha256": {name: sha256(members[name]) for name in sorted(RUNTIME_FILES)},
    }


def clean_environment() -> dict[str, str]:
    """Allow only OS plumbing; no inherited credentials, proxies or installer overrides."""
    allowed = {
        "PATH",
        "PATHEXT",
        "SYSTEMROOT",
        "WINDIR",
        "COMSPEC",
        "TEMP",
        "TMP",
        "TMPDIR",
        "HOME",
        "USERPROFILE",
        "LOCALAPPDATA",
        "APPDATA",
        "LANG",
        "LC_ALL",
    }
    return {key: value for key, value in os.environ.items() if key.upper() in allowed}


def run_command(command: list[str], cwd: Path, commands: list[dict[str, Any]]) -> str:
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=clean_environment(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    commands.append(
        {
            "argv": command,
            "cwd": str(cwd),
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
    )
    completed.check_returncode()
    return completed.stdout


# This runs in the newly installed environment, not in this script's interpreter.
PROBE = """\
import hashlib
import importlib
import json
import sys
from importlib.metadata import distribution, distributions
from importlib.resources import files
from pathlib import Path


def check(condition, message):
    if not condition:
        raise RuntimeError(message)


expected = json.loads(sys.argv[1])
venv = Path(expected["venv"]).resolve()
check(sys.flags.isolated == 1 and sys.flags.optimize == 0, "Python must be isolated and unoptimized")
check(Path(sys.prefix).resolve() == venv and sys.prefix != sys.base_prefix, "wrong virtual environment")
installed = sorted(item.metadata["Name"] for item in distributions())
check(installed == [expected["name"]], "unexpected installed distributions: " + repr(installed))
metadata = distribution(expected["name"])
check(not metadata.requires, "installed distribution declares dependencies")
for field, values in expected["metadata"].items():
    check(sorted(metadata.metadata.get_all(field, [])) == sorted(values), "installed metadata: " + field)
recorded = {str(item).replace("\\\\", "/") for item in metadata.files or ()}
for name, digest in expected["member_sha256"].items():
    if name.endswith("/RECORD"):
        continue  # Installers legitimately add INSTALLER/direct_url.json/REQUESTED to RECORD.
    path = Path(metadata.locate_file(name)).resolve(strict=True)
    check(name in recorded and path.is_relative_to(venv), "file is not installed inside venv: " + name)
    check(hashlib.sha256(path.read_bytes()).hexdigest() == digest, "installed bytes differ: " + name)
for module_name, relative in (("ordered_btree", "ordered_btree/__init__.py"),
                              ("ordered_btree._tree", "ordered_btree/_tree.py")):
    module = importlib.import_module(module_name)
    actual = Path(module.__file__).resolve(strict=True)
    check(actual.is_relative_to(venv), "import escaped venv: " + str(actual))
    check(actual == Path(metadata.locate_file(relative)).resolve(strict=True), "import differs from distribution")
check(files("ordered_btree").joinpath("py.typed").is_file(), "missing installed py.typed")
from ordered_btree import BTree, ConcurrentModificationError

tree = BTree[int](32, range(1000))
check(list(tree.range(900, 910)) == list(range(900, 910)), "half-open range failed")
check(tree.search(500) == 500, "search failed")
snapshot = tree.snapshot()
iterator = iter(tree)
check(tree.delete(500) is True, "delete failed")
try:
    next(iterator)
except ConcurrentModificationError:
    pass
else:
    raise RuntimeError("iterator did not invalidate")
tree.validate()
check(500 in snapshot, "snapshot was not detached")
copy = tree.copy()
while copy:
    copy.pop_min()
copy.validate()
check(len(tree) == 999, "copy changed original")
print(json.dumps({"status": "passed", "python": sys.version, "executable": sys.executable,
                  "isolated": sys.flags.isolated, "venv": str(venv),
                  "package_file": str(Path(importlib.import_module("ordered_btree").__file__).resolve()),
                  "installed_distributions": installed}))
"""


def smoke_wheel(wheel: Path, project: Path, commands: list[dict[str, Any]]) -> dict[str, Any]:
    inspection = inspect_wheel(wheel, project)
    with tempfile.TemporaryDirectory(prefix="ordered-btree-wheel-") as temporary:
        root = Path(temporary).resolve()
        require(
            not root.is_relative_to(project.resolve()) and not root.is_relative_to(DEFAULT_PROJECT),
            "smoke temporary directory must be outside the checkout",
        )
        env = root / "venv"
        python = env / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        run_command(
            [
                "uv",
                "--no-config",
                "--offline",
                "venv",
                "--no-project",
                "--no-python-downloads",
                "--python",
                sys.executable,
                str(env),
            ],
            root,
            commands,
        )
        run_command(
            [
                "uv",
                "--no-config",
                "--offline",
                "pip",
                "install",
                "--python",
                str(python),
                "--no-index",
                "--no-deps",
                "--no-build",
                "--link-mode",
                "copy",
                str(wheel.resolve()),
            ],
            root,
            commands,
        )
        probe = root / "probe.py"
        probe.write_text(PROBE, encoding="utf-8")
        expected = {**inspection, "venv": str(env)}
        result = run_command([str(python), "-I", str(probe), json.dumps(expected)], root, commands)
        smoke = json.loads(result)
    require(sha256(wheel.read_bytes()) == inspection["sha256"], "wheel changed during smoke")
    return {"inspection": inspection, "smoke": smoke, "probe_sha256": sha256(PROBE.encode())}


def provenance() -> dict[str, Any]:
    return {"python": sys.version, "executable": sys.executable, "platform": platform.platform()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path)
    parser.add_argument("--project", type=Path, default=DEFAULT_PROJECT)
    args = parser.parse_args()
    if sys.flags.optimize:
        parser.error("optimized Python (-O/-OO) is not supported")
    report: dict[str, Any] = {"status": "failed", "runtime": provenance(), "commands": []}
    try:
        report.update(smoke_wheel(args.wheel, args.project, report["commands"]))
        report["status"] = "passed"
    except (
        OSError,
        ValueError,
        KeyError,
        csv.Error,
        zipfile.BadZipFile,
        subprocess.CalledProcessError,
    ) as error:
        report["error"] = str(error)
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
