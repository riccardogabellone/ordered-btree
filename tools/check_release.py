"""Conservative publication preflight. Never uploads or changes files."""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path
from urllib.parse import urlsplit


def license_files_exist(root: Path, patterns: object) -> bool:
    if not isinstance(patterns, list) or not patterns:
        return False
    for pattern in patterns:
        if not isinstance(pattern, str) or not pattern or ".." in Path(pattern).parts:
            return False
        try:
            matches = list(root.glob(pattern))
        except (ValueError, NotImplementedError):
            return False
        if not matches or any(
            not path.is_file()
            or path.is_symlink()
            or not path.resolve().is_relative_to(root.resolve())
            or not path.stat().st_size
            for path in matches
        ):
            return False
    return True


def valid_repository(value: object) -> bool:
    if not isinstance(value, str) or any(char.isspace() for char in value):
        return False
    try:
        url = urlsplit(value)
        return (
            url.scheme in {"https", "http"}
            and bool(url.hostname)
            and bool(url.path.strip("/"))
            and url.username is None
            and url.password is None
            and not url.query
            and not url.fragment
        )
    except ValueError:
        return False


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    config = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    project = config["project"]
    errors = []
    if any(c.startswith("Private ::") for c in project.get("classifiers", [])):
        errors.append("remove the Private classifier only after owner approval")
    release = config.get("tool", {}).get("ordered-btree", {}).get("release", {})
    if release.get("name-confirmed") is not True:
        errors.append("confirm the distribution name and set name-confirmed = true")
    if release.get("publication-approved") is not True:
        errors.append("obtain explicit publication approval and set publication-approved = true")
    if not isinstance(project.get("license"), str) or not project["license"].strip():
        errors.append("provide a license expression chosen by the owner")
    if not license_files_exist(root, project.get("license-files")):
        errors.append(
            "provide license-files patterns matching nonempty license files inside the project"
        )
    people = project.get("authors", []) + project.get("maintainers", [])
    if not people or any(
        not isinstance(person, dict)
        or not any(
            isinstance(person.get(key), str) and person[key].strip() for key in ("name", "email")
        )
        for person in people
    ):
        errors.append("provide actual nonempty author or maintainer metadata")
    if not valid_repository(project.get("urls", {}).get("Repository")):
        errors.append("provide an actual public HTTP(S) Repository URL without credentials")
    if errors:
        print("Publication preflight blocked:")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("Local metadata preflight passed. Name ownership, license review, tests,")
    print("artifact validation, and remote publication are still separate steps.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
