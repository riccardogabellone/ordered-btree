"""Small stdlib-only report support shared by the two verification runners."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import sys
import sysconfig
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4


def require_assertions() -> None:
    if not __debug__:
        raise RuntimeError("verification requires assertions; remove -O/-OO/PYTHONOPTIMIZE")


def source_record(path: str | Path) -> dict[str, str]:
    source = Path(path).resolve(strict=True)
    return {"path": str(source), "sha256": hashlib.sha256(source.read_bytes()).hexdigest()}


def execution_metadata(runner: Path) -> dict[str, Any]:
    sources = {"runner": source_record(runner)}
    for name, module in tuple(sys.modules.items()):
        if (
            name == "ordered_btree"
            or name.startswith("ordered_btree.")
            or name in {"tools._reports", "tests.support"}
        ):
            filename = getattr(module, "__file__", None)
            if filename is not None:
                sources[name] = source_record(filename)
    return {
        "python": sys.version,
        "executable": sys.executable,
        "prefix": sys.prefix,
        "base_prefix": sys.base_prefix,
        "platform": platform.platform(),
        "argv": list(sys.argv),
        "interpreter_argv": list(sys.orig_argv),
        "cwd": str(Path.cwd()),
        "optimization": sys.flags.optimize,
        "gil_enabled": getattr(sys, "_is_gil_enabled", lambda: None)(),
        "py_gil_disabled": sysconfig.get_config_var("Py_GIL_DISABLED"),
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "sources": sources,
    }


def write_report(path: Path, report: dict[str, Any], *, exclusive: bool = False) -> None:
    """Publish complete JSON atomically; exclusive publication never replaces a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            json.dump(report, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        if exclusive:
            # A hard link publishes a complete file without the check/replace race.
            # The temporary file is on the same filesystem and is unlinked below.
            os.link(temporary, path)
        else:
            os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


@contextmanager
def report_run(
    name: str,
    output: Path | None,
    runner: Path,
    details: dict[str, Any],
) -> Iterator[tuple[Path, dict[str, Any]]]:
    require_assertions()
    if output is None:
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
        output = Path("results") / f"{name}-{stamp}-{uuid4().hex[:8]}" / f"{name}.json"
    output = output.absolute()
    if output.exists():
        raise FileExistsError(f"report already exists; choose a fresh output path: {output}")
    report = execution_metadata(runner) | details | {"status": "started"}
    write_report(output, report, exclusive=True)
    begin = time.perf_counter()
    try:
        yield output, report
    except BaseException as error:
        report.update(
            {
                "status": "failed",
                "error": {"type": type(error).__name__, "message": str(error)},
                "elapsed_seconds": time.perf_counter() - begin,
                "completed_at_utc": datetime.now(UTC).isoformat(),
            }
        )
        write_report(output, report)
        raise
    else:
        report.update(
            {
                "status": "passed",
                "elapsed_seconds": time.perf_counter() - begin,
                "completed_at_utc": datetime.now(UTC).isoformat(),
            }
        )
        write_report(output, report)


# Imported by both command-line runners before any verification work begins.
require_assertions()
