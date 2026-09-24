"""Read-only release checks and fresh upload staging; this tool never publishes.

CI creates one manifest and an immutable wheel/sdist pair. Every handoff checks
both against the exact source commit. Index recovery stages only missing bytes
from that pair, never a rebuild or a blanket skip-existing upload.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

if TYPE_CHECKING:
    from tools import verify_dist, wheel_smoke
elif __package__:
    from . import verify_dist, wheel_smoke
else:
    import verify_dist
    import wheel_smoke

require = wheel_smoke.require
INDEXES = {
    "pypi": ("pypi.org", "files.pythonhosted.org"),
    "testpypi": ("test.pypi.org", "test-files.pythonhosted.org"),
}


def git(project: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(project), *arguments],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        timeout=60,
        env=wheel_smoke.clean_environment(),
    )
    require(
        result.returncode == 0, f"source git {' '.join(arguments)} failed: {result.stderr.strip()}"
    )
    return result.stdout.strip()


def check_provenance(project: Path, ref: str, event_sha: str) -> dict[str, str]:
    version = wheel_smoke.project_metadata(project)["version"]
    require(re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version), "release version must be final X.Y.Z")
    require(ref == f"refs/tags/v{version}", "tag must exactly match the project version")
    require(re.fullmatch(r"[0-9a-f]{40}", event_sha), "expected a full event SHA")
    require(
        git(project, "rev-parse", "--is-shallow-repository") == "false", "need full main history"
    )
    commit = git(project, "rev-parse", "--verify", f"{ref}^{{commit}}")
    require(
        git(project, "rev-parse", "--verify", f"{event_sha}^{{commit}}") == commit,
        "event SHA does not identify the tagged commit",
    )
    require(git(project, "rev-parse", "HEAD") == commit, "checkout HEAD is not the tagged commit")
    main = git(project, "rev-parse", "--verify", "refs/remotes/origin/main^{commit}")
    git(project, "merge-base", "--is-ancestor", commit, "refs/remotes/origin/main")
    return {"source_sha": commit, "version": version, "tag": f"v{version}", "main_sha": main}


def make_manifest(directory: Path, project: Path, source_sha: str) -> dict[str, Any]:
    require(re.fullmatch(r"[0-9a-f]{40}", source_sha), "expected full source SHA")
    require(git(project, "rev-parse", "HEAD") == source_sha, "source SHA differs from checkout")
    git(project, "diff", "--quiet", "HEAD", "--")
    files = verify_dist.distribution_pair(directory, project)
    source = {}
    for name in git(project, "ls-files", "-z").split("\0"):
        if not name:
            continue
        path = project / name
        require(path.is_file() and not path.is_symlink(), f"unsafe/missing source: {name}")
        source[name] = wheel_smoke.sha256(path.read_bytes())
    require("pyproject.toml" in source, "source must be a tracked project")
    metadata = wheel_smoke.project_metadata(project)
    return {
        "schema": 1,
        "name": metadata["name"],
        "version": metadata["version"],
        "source_sha": source_sha,
        "source_sha256": source,
        "files": {
            path.name: {
                "sha256": wheel_smoke.sha256(path.read_bytes()),
                "size": path.stat().st_size,
            }
            for path in files
        },
    }


def check_manifest(
    directory: Path, project: Path, manifest: dict[str, Any], source_sha: str
) -> None:
    require(
        manifest == make_manifest(directory, project, source_sha),
        "manifest differs from source or distribution bytes",
    )


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(value, indent=2, sort_keys=True) + "\n")


def write_manifest(path: Path, manifest: dict[str, Any]) -> str:
    write_json(path, manifest)
    with (path.parent / "SHA256SUMS").open("x", encoding="utf-8", newline="\n") as stream:
        for name, item in sorted(manifest["files"].items()):
            stream.write(f"{item['sha256']}  {name}\n")
    return wheel_smoke.sha256(path.read_bytes())


def read_manifest(path: Path, digest: str) -> dict[str, Any]:
    require(re.fullmatch(r"[0-9a-f]{64}", digest), "expected manifest SHA256 digest")
    data = path.read_bytes()
    require(wheel_smoke.sha256(data) == digest, "manifest artifact digest mismatch")
    value = json.loads(data)
    if not isinstance(value, dict):
        raise ValueError("manifest must be an object")
    return value


def official_url(url: str) -> None:
    parsed = urlsplit(url)
    require(
        parsed.scheme == "https"
        and parsed.hostname in {host for hosts in INDEXES.values() for host in hosts}
        and parsed.port in (None, 443)
        and parsed.username is None
        and parsed.password is None
        and not parsed.query
        and not parsed.fragment
        and not any(char.isspace() for char in url),
        "expected an official, credential-free index URL",
    )


class OfficialRedirect(HTTPRedirectHandler):
    def redirect_request(
        self, req: Request, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> Request | None:
        official_url(newurl)  # Validate BEFORE following, not just after downloading.
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(url: str, limit: int) -> bytes:
    official_url(url)
    request = Request(url, headers={"User-Agent": "ordered-btree-release-check/1"})
    with build_opener(OfficialRedirect()).open(request, timeout=30) as response:
        official_url(response.geturl())
        data: bytes = response.read(limit + 1)
    require(len(data) <= limit, "index response exceeds verification size limit")
    return data


def check_index_json(
    data: bytes,
    index: str,
    manifest: dict[str, Any],
    project: Path,
) -> dict[str, str]:
    payload = json.loads(data)
    require(isinstance(payload, dict), "index JSON must be an object")
    info = payload.get("info")
    require(isinstance(info, dict), "missing index metadata")
    require(
        info.get("name") == manifest["name"] and info.get("version") == manifest["version"],
        "index name/version mismatch",
    )
    require(
        info.get("project_urls") == wheel_smoke.project_metadata(project).get("urls", {}),
        "index Project-URL links mismatch",
    )
    rows = payload.get("urls")
    require(isinstance(rows, list), "missing index file list")
    files: dict[str, str] = {}
    for row in rows:
        require(isinstance(row, dict), "malformed index file")
        name = row.get("filename")
        require(
            isinstance(name, str) and name in manifest["files"] and name not in files,
            "unknown or duplicate index file",
        )
        expected = manifest["files"][name]
        require(
            isinstance(row.get("digests"), dict)
            and row["digests"].get("sha256") == expected["sha256"],
            f"index digest conflict: {name}",
        )
        require(
            row.get("size") == expected["size"] and row.get("yanked") is False,
            f"index file size/yanked conflict: {name}",
        )
        url = row.get("url")
        require(isinstance(url, str), "missing index file URL")
        official_url(url)
        require(urlsplit(url).hostname == INDEXES[index][1], "wrong index download host")
        files[name] = url
    return files


def wait_for_index(
    index: str,
    manifest: dict[str, Any],
    project: Path,
    *,
    complete: bool,
    attempts: int = 12,
) -> dict[str, str]:
    require(index in INDEXES, "only official pypi/testpypi indexes are supported")
    require(1 <= attempts <= 12, "visibility attempts must be between 1 and 12")
    url = f"https://{INDEXES[index][0]}/pypi/{manifest['name']}/{manifest['version']}/json"
    for attempt in range(attempts):
        try:
            data = fetch(url, 2 * 1024 * 1024)
        except HTTPError as error:
            if error.code == 404:
                if not complete:
                    return {}
            elif error.code != 429 and not 500 <= error.code < 600:
                raise
        except (URLError, TimeoutError, ConnectionError):
            pass
        else:
            files = check_index_json(data, index, manifest, project)
            if not complete or set(files) == set(manifest["files"]):
                return files
        if attempt + 1 < attempts:
            time.sleep(5)
    raise ValueError(f"{index} exact release not visible after {attempts} attempts")


def stage_missing(
    directory: Path,
    project: Path,
    manifest: dict[str, Any],
    index: str,
    upload: Path,
) -> dict[str, Any]:
    if upload.exists():
        raise FileExistsError(upload)
    check_manifest(directory, project, manifest, manifest["source_sha"])
    files = wait_for_index(index, manifest, project, complete=False)
    missing = sorted(manifest["files"].keys() - files.keys())
    upload.mkdir(parents=True)
    for name in missing:
        destination = upload / name
        shutil.copyfile(directory / name, destination)
        require(
            wheel_smoke.sha256(destination.read_bytes()) == manifest["files"][name]["sha256"],
            f"staged digest mismatch: {name}",
        )
    return {
        "index": index,
        "existing": sorted(files),
        "missing": missing,
        "source_sha": manifest["source_sha"],
    }


def _download_distribution(url: str) -> bytes:
    """Bound transient CDN failures like index visibility; never retry invalid bytes/URLs."""
    for attempt in range(12):
        try:
            return fetch(url, wheel_smoke.MAX_UNPACKED_BYTES)
        except HTTPError as error:
            if error.code not in {404, 429} and not 500 <= error.code < 600:
                raise
        except (URLError, TimeoutError, ConnectionError):
            pass
        if attempt + 1 < 12:
            time.sleep(5)
    raise ValueError(f"distribution download unavailable after 12 attempts: {url}")


def verify_index(
    directory: Path,
    project: Path,
    manifest: dict[str, Any],
    index: str,
    report: dict[str, Any],
) -> None:
    check_manifest(directory, project, manifest, manifest["source_sha"])
    files = wait_for_index(index, manifest, project, complete=True)
    report.update({"index": index, "source_sha": manifest["source_sha"], "indexed_urls": files})
    with tempfile.TemporaryDirectory(prefix="ordered-btree-index-") as temporary:
        downloaded = Path(temporary)
        for name, url in files.items():
            data = _download_distribution(url)
            expected = manifest["files"][name]
            require(
                len(data) == expected["size"] and wheel_smoke.sha256(data) == expected["sha256"],
                f"download digest/size mismatch: {name}",
            )
            (downloaded / name).write_bytes(data)
        wheel, _ = verify_dist.distribution_pair(downloaded, project)
        # The exact indexed wheel is installed offline, with no token/index fallback,
        # into an external fresh venv. The existing -I probe checks every installed byte.
        report["installed"] = wheel_smoke.smoke_wheel(wheel, project, report["commands"])
    report["status"] = "passed"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("provenance", "manifest", "check", "stage", "verify-index"):
        command = commands.add_parser(name)
        command.add_argument("--project", type=Path, default=wheel_smoke.DEFAULT_PROJECT)
        command.add_argument("--sha", required=True)
        command.add_argument("--report", type=Path)
        if name == "provenance":
            command.add_argument("--ref", required=True)
        else:
            command.add_argument("--dist", type=Path, required=True)
            if name == "manifest":
                command.add_argument("--output", type=Path, required=True)
            else:
                command.add_argument("--manifest", type=Path, required=True)
                command.add_argument("--manifest-sha256", required=True)
        if name in {"stage", "verify-index"}:
            command.add_argument("--index", choices=INDEXES, required=True)
        if name == "stage":
            command.add_argument("--upload-dir", type=Path, required=True)
    args = parser.parse_args()
    if sys.flags.optimize:
        parser.error("optimized Python is not supported")
    report: dict[str, Any] = {
        "status": "failed",
        "runtime": wheel_smoke.provenance(),
        "commands": [],
    }
    try:
        if args.command == "provenance":
            result = check_provenance(args.project, args.ref, args.sha)
            report.update(result)
            for name in ("source_sha", "version", "tag"):
                print(f"{name}={result[name]}")
        elif args.command == "manifest":
            value = make_manifest(args.dist, args.project, args.sha)
            print(f"manifest_sha256={write_manifest(args.output, value)}")
        else:
            value = read_manifest(args.manifest, args.manifest_sha256)
            check_manifest(args.dist, args.project, value, args.sha)
            if args.command == "stage":
                staged = stage_missing(args.dist, args.project, value, args.index, args.upload_dir)
                report.update(staged)
                print(f"missing_count={len(staged['missing'])}")
            elif args.command == "verify-index":
                verify_index(args.dist, args.project, value, args.index, report)
        report["status"] = "passed"
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        report["error"] = str(error)
        print(str(error), file=sys.stderr)
    if args.report:
        write_json(args.report, report)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
