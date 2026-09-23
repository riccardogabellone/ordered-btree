"""Regression tests for the verification tools, not the B-tree algorithms."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import ordered_btree
from ordered_btree import BTree

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = {
    "stress": ROOT / "tools" / "stress.py",
    "benchmark": ROOT / "benchmarks" / "benchmark.py",
}
SMALL_ARGS = {
    "stress": ["--quick"],
    "benchmark": [
        "--n",
        "20",
        "--probes",
        "10",
        "--ranges",
        "3",
        "--repeats",
        "1",
        "--degrees",
        "2",
    ],
}


def load_runner(name):
    spec = importlib.util.spec_from_file_location(f"_test_{name}_runner", SCRIPTS[name])
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def source_environment():
    environment = os.environ.copy()
    environment.pop("PYTHONOPTIMIZE", None)
    environment["PYTHONPATH"] = os.pathsep.join([str(ROOT / "src"), str(ROOT)])
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return environment


def invoke_main(monkeypatch, name, runner, output=None):
    argv = [str(SCRIPTS[name]), *SMALL_ARGS[name]]
    if output is not None:
        argv.extend(["--output", str(output)])
    monkeypatch.setattr(sys, "argv", argv)
    runner.main()
    return argv


@pytest.mark.parametrize("name", SCRIPTS)
@pytest.mark.parametrize("optimization", ["-O", "-OO", "environment"])
def test_optimized_tools_fail_before_creating_a_report(tmp_path, name, optimization):
    output = tmp_path / "report.json"
    environment = source_environment()
    flags = [] if optimization == "environment" else [optimization]
    if optimization == "environment":
        environment["PYTHONOPTIMIZE"] = "1"
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            *flags,
            str(SCRIPTS[name]),
            *SMALL_ARGS[name],
            "--output",
            str(output),
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert result.returncode != 0, result.stdout
    assert "assertions" in result.stderr.lower()
    assert not output.exists()


@pytest.mark.parametrize("name", SCRIPTS)
def test_existing_explicit_report_is_refused_before_work(tmp_path, monkeypatch, name):
    output = tmp_path / "previous.json"
    original = '{"status": "passed", "run": "previous"}\n'
    output.write_text(original, encoding="utf-8")
    runner = load_runner(name)

    def must_not_run(*args, **kwargs):
        pytest.fail("verification began before rejecting an existing report")

    monkeypatch.setattr(runner, "exhaustive" if name == "stress" else "run_case", must_not_run)
    with pytest.raises(FileExistsError):
        invoke_main(monkeypatch, name, runner, output)
    assert output.read_text(encoding="utf-8") == original


@pytest.mark.parametrize("name", SCRIPTS)
def test_first_phase_failure_records_started_then_failed(tmp_path, monkeypatch, name):
    output = tmp_path / "failed.json"
    runner = load_runner(name)
    observed = []

    class InjectedFailure(Exception):
        pass

    def fail(*args, **kwargs):
        if output.exists():
            observed.append(json.loads(output.read_text(encoding="utf-8"))["status"])
        raise InjectedFailure("first phase failed")

    monkeypatch.setattr(runner, "exhaustive" if name == "stress" else "run_case", fail)
    with pytest.raises(InjectedFailure, match="first phase failed"):
        invoke_main(monkeypatch, name, runner, output)
    assert observed == ["started"]
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["status"] == "failed"
    assert report["error"] == {"type": "InjectedFailure", "message": "first phase failed"}
    assert report["elapsed_seconds"] >= 0
    assert report["completed_at_utc"] >= report["timestamp_utc"]


@pytest.mark.parametrize("name", SCRIPTS)
def test_default_reports_are_unique_and_leave_history_untouched(tmp_path, monkeypatch, name):
    monkeypatch.chdir(tmp_path)
    historical = tmp_path / "results" / f"{name}.json"
    historical.parent.mkdir()
    historical.write_text('{"historical": true}\n', encoding="utf-8")
    runner = load_runner(name)
    invoke_main(monkeypatch, name, runner)
    invoke_main(monkeypatch, name, runner)
    reports = [path for path in tmp_path.rglob("*.json") if path != historical]
    assert len(reports) == 2
    assert historical.read_text(encoding="utf-8") == '{"historical": true}\n'
    assert all(
        json.loads(path.read_text(encoding="utf-8"))["status"] == "passed" for path in reports
    )


@pytest.mark.parametrize("name", SCRIPTS)
def test_reports_fingerprint_loaded_code_and_execution(tmp_path, monkeypatch, name):
    output = tmp_path / "report.json"
    runner = load_runner(name)
    argv = invoke_main(monkeypatch, name, runner, output)
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["status"] == "passed"
    assert Path(report["executable"]).resolve() == Path(sys.executable).resolve()
    assert report["argv"] == argv
    assert report["interpreter_argv"] == sys.orig_argv
    assert report["optimization"] == 0
    assert report["gil_enabled"] == getattr(sys, "_is_gil_enabled", lambda: None)()
    sources = {
        "ordered_btree": Path(ordered_btree.__file__),
        "ordered_btree._tree": Path(sys.modules[BTree.__module__].__file__),
        "tools._reports": ROOT / "tools" / "_reports.py",
        "runner": SCRIPTS[name],
    }
    if name == "stress":
        sources["tests.support"] = ROOT / "tests" / "support.py"
    for label, path in sources.items():
        assert report["sources"][label] == {
            "path": str(path.resolve()),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }


def test_report_preserves_the_invoked_executable_and_environment(tmp_path, monkeypatch):
    from tools import _reports

    executable = str(tmp_path / "links" / ".." / "environment" / "python.exe")
    monkeypatch.setattr(sys, "executable", executable)
    metadata = _reports.execution_metadata(SCRIPTS["benchmark"])
    assert metadata["executable"] == executable
    assert metadata["prefix"] == sys.prefix
    assert metadata["base_prefix"] == sys.base_prefix


def test_partial_report_write_preserves_the_previous_complete_record(tmp_path, monkeypatch):
    from tools import _reports

    output = tmp_path / "report.json"
    previous = '{"status": "started"}\n'
    output.write_text(previous, encoding="utf-8")

    def interrupted_dump(report, stream, **kwargs):
        stream.write('{"status":')
        raise OSError("injected write failure")

    monkeypatch.setattr(_reports.json, "dump", interrupted_dump)
    with pytest.raises(OSError, match="injected write failure"):
        _reports.write_report(output, {"status": "passed"})
    assert output.read_text(encoding="utf-8") == previous
    assert list(tmp_path.iterdir()) == [output]


def test_exclusive_report_creation_never_replaces_existing_data(tmp_path):
    from tools import _reports

    output = tmp_path / "report.json"
    previous = '{"status": "passed", "run": "earlier"}\n'
    output.write_text(previous, encoding="utf-8")
    with pytest.raises(FileExistsError):
        _reports.write_report(output, {"status": "started"}, exclusive=True)
    assert output.read_text(encoding="utf-8") == previous
    assert list(tmp_path.iterdir()) == [output]


def test_stress_phases_report_the_seeds_they_actually_use(monkeypatch):
    runner = load_runner("stress")
    random_factory = runner.random.Random
    seeds = []

    def random_with_recorded_seed(seed):
        seeds.append(seed)
        return random_factory(seed)

    monkeypatch.setattr(runner.random, "Random", random_with_recorded_seed)
    matrix = runner.order_matrix(4)
    large = runner.large(10, 4)
    assert [matrix["seed"], large["seed"]] == seeds


def test_benchmark_rejects_wrong_range_values_even_when_lengths_match():
    class WrongRange(BTree):
        def range(self, start=None, stop=None):
            return iter([-999] * 10)

    with pytest.raises(AssertionError):
        load_runner("benchmark").run_case(
            WrongRange,
            2,
            list(range(20)),
            [0, 10, 30],
            list(range(20)),
            [(10, 20)],
            1,
        )


def test_benchmark_rejects_wrong_membership_even_when_hit_totals_match():
    class WrongMembership(BTree):
        def __contains__(self, key):
            return not super().__contains__(key)

    with pytest.raises(AssertionError):
        load_runner("benchmark").run_case(
            WrongMembership,
            2,
            list(range(20)),
            [0, 10, 20, 30],
            list(range(20)),
            [(10, 20)],
            1,
        )


def test_benchmark_checks_individual_queries_outside_timed_regions(monkeypatch):
    runner = load_runner("benchmark")
    original_elapsed = runner.elapsed_ms
    timing = False
    observed = {"contains": set(), "range": set()}

    class ObservedTree(BTree):
        def __contains__(self, key):
            observed["contains"].add(timing)
            return super().__contains__(key)

        def range(self, start=None, stop=None):
            observed["range"].add(timing)
            return super().range(start, stop)

    def elapsed(call):
        nonlocal timing
        timing = True
        try:
            return original_elapsed(call)
        finally:
            timing = False

    monkeypatch.setattr(runner, "elapsed_ms", elapsed)
    result = runner.run_case(
        ObservedTree,
        2,
        list(range(20)),
        [0, 10, 30],
        list(range(20)),
        [(10, 20)],
        1,
    )
    assert observed == {"contains": {False, True}, "range": {False, True}}
    assert len(result["samples"]) == 1
    assert set(result["samples"][0]) == {
        "insert_ms",
        "search_ms",
        "iterate_ms",
        "ranges_ms",
        "repr_ms",
        "delete_ms",
    }


def test_missing_hypothesis_is_an_import_failure_not_a_skip():
    code = """
import importlib.abc
import json
import sys
class MissingHypothesis(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "hypothesis" or fullname.startswith("hypothesis."):
            raise ModuleNotFoundError("hypothesis deliberately unavailable", name="hypothesis")
sys.meta_path.insert(0, MissingHypothesis())
try:
    import tests.test_hypothesis
except BaseException as error:
    print(json.dumps({"error": type(error).__name__, "name": getattr(error, "name", None)}))
else:
    raise SystemExit("the missing dependency was ignored")
"""
    result = subprocess.run(
        [sys.executable, "-B", "-c", code],
        cwd=ROOT,
        env=source_environment(),
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    assert json.loads(result.stdout) == {"error": "ModuleNotFoundError", "name": "hypothesis"}


@pytest.mark.parametrize("last", [False, True])
def test_state_machine_grows_and_drains_internal_high_degree_trees(last):
    from .test_hypothesis import TreeMachine

    machine = TreeMachine()
    try:
        machine.create(degree=128)
        assert machine.tree.height() >= 2
        machine.agrees_with_model()
        machine.drain(last=last)
        assert len(machine.tree) == 0 and not machine.model
        machine.grow()
        assert machine.tree.height() >= 2
        machine.agrees_with_model()
        machine.clear()
        machine.grow()
        assert machine.tree.height() >= 2
        machine.agrees_with_model()
    finally:
        machine.teardown()
