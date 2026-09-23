"""Consumer typing checks reject misuse as well as accepting valid programs."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    ("statement", "diagnostic"),
    [
        ('tree.insert("not an int")', "arg-type"),
        ('tree.search("not an int")', "arg-type"),
        ("tree.insert(None)", "arg-type"),
        ("tree.t = 8", "read-only"),
        ("tree.inspect().keys = (1,)", "read-only"),
    ],
)
def test_consumer_type_misuse_is_rejected(tmp_path: Path, statement: str, diagnostic: str) -> None:
    source = tmp_path / "consumer.py"
    source.write_text(
        "from ordered_btree import BTree\ntree = BTree[int]()\n" + statement + "\n",
        encoding="utf-8",
    )
    config = tmp_path / "mypy.ini"
    config.write_text("[mypy]\nstrict = True\npython_version = 3.12\n", encoding="utf-8")
    environment = os.environ.copy()
    environment.pop("MYPYPATH", None)
    environment.pop("PYTHONPATH", None)
    result = subprocess.run(
        [sys.executable, "-I", "-m", "mypy", "--config-file", str(config), str(source)],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert "Found 1 error in 1 file" in result.stdout
    assert diagnostic in result.stdout
    assert "import-not-found" not in result.stdout
