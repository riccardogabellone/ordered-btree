"""Deterministic differential stress tests; no third-party test dependency.

Run after installation: python tools/stress.py (creates a fresh run report).
Use --quick for a smaller local check. Report timings include validation and
reference-model work and are NOT data-structure benchmarks.
"""

from __future__ import annotations

import argparse
import bisect
import itertools
import json
import random
import sys
import time
from collections import Counter
from pathlib import Path

# Only add test/tool support, never src: exercise the selected installed library.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ordered_btree import BTree
from tests.support import check_int_tree
from tools._reports import report_run, write_report


def exhaustive(n: int) -> dict:
    permutations = list(itertools.permutations(range(n)))
    histories = 0
    for insertion in permutations:
        for deletion in permutations:
            tree = BTree[int]()
            model: list[int] = []
            for key in insertion:
                inserted = tree.insert(key)
                assert inserted
                bisect.insort(model, key)
                check_int_tree(tree, model)
            for key in deletion:
                deleted = tree.delete(key)
                assert deleted
                model.remove(key)
                check_int_tree(tree, model)
            histories += 1
    return {"degree": 2, "keys": n, "histories": histories, "check_frequency": "every mutation"}


def random_histories(steps: int, degrees: list[int], seeds: list[int]) -> dict:
    counts: Counter[str] = Counter()
    for degree in degrees:
        for seed in seeds:
            rng = random.Random(seed)
            tree = BTree[int](degree)
            model: list[int] = []
            for step in range(steps):
                op = rng.randrange(10)
                key = rng.randrange(-2000, 2001)
                index = bisect.bisect_left(model, key)
                present = index < len(model) and model[index] == key
                if op < 4:
                    counts["insert"] += 1
                    inserted = tree.insert(key)
                    assert inserted == (not present)
                    if not present:
                        model.insert(index, key)
                elif op < 7:
                    counts["delete"] += 1
                    deleted = tree.delete(key)
                    assert deleted == present
                    if present:
                        model.pop(index)
                elif op < 9:
                    counts["search"] += 1
                    assert tree.search(key) == (key if present else None)
                    assert (key in tree) == present
                else:
                    counts["range"] += 1
                    lo = None if rng.randrange(8) == 0 else rng.randrange(-2100, 2101)
                    hi = None if rng.randrange(8) == 0 else rng.randrange(-2100, 2101)
                    a = 0 if lo is None else bisect.bisect_left(model, lo)
                    b = len(model) if hi is None else bisect.bisect_left(model, hi)
                    assert list(tree.range(lo, hi)) == model[a:b]
                if step % 257 == 0:
                    check_int_tree(tree, model)
            check_int_tree(tree, model)
    return {
        "degrees": degrees,
        "seeds": seeds,
        "steps_per_history": steps,
        "total_operations": sum(counts.values()),
        "operation_counts": dict(counts),
        "check_frequency": "every 257 operations and at end",
    }


def order_matrix(n: int) -> dict:
    seed = 567
    asc = list(range(n))
    shuffled = asc.copy()
    random.Random(seed).shuffle(shuffled)
    extremes = []
    a, b = 0, n - 1
    while a <= b:
        extremes.append(a)
        if a != b:
            extremes.append(b)
        a += 1
        b -= 1
    orders = [asc, asc[::-1], shuffled, extremes]
    histories = 0
    for degree in [2, 3, 8, 32]:
        for insertion in orders:
            for deletion in orders:
                tree = BTree[int](degree, insertion)
                check_int_tree(tree, asc)
                remaining = set(asc)
                for i, key in enumerate(deletion):
                    deleted = tree.delete(key)
                    assert deleted
                    remaining.remove(key)
                    if i % 503 == 0:
                        check_int_tree(tree, sorted(remaining))
                check_int_tree(tree, [])
                histories += 1
    return {"keys": n, "histories": histories, "degrees": [2, 3, 8, 32], "seed": seed}


def large(n: int, ranges: int) -> dict:
    seed = 9182
    rng = random.Random(seed)
    values = list(range(n))
    rng.shuffle(values)
    tree = BTree[int](32)
    for key in values:
        inserted = tree.insert(key)
        assert inserted
    check_int_tree(tree, list(range(n)))
    for key in values:
        assert tree.search(key) == key
        assert tree.search(key + n) is None
    for _ in range(ranges):
        lo = rng.randrange(-100, n + 100)
        hi = lo + rng.randrange(0, 80)
        assert list(tree.range(lo, hi)) == list(range(max(0, lo), min(n, hi)))
    rng.shuffle(values)
    model = set(values)
    for i, key in enumerate(values):
        deleted = tree.delete(key)
        assert deleted
        model.remove(key)
        if i % max(1, n // 10) == 0:
            check_int_tree(tree, sorted(model))
    check_int_tree(tree, [])
    return {
        "degree": 32,
        "inserts": n,
        "probes": 2 * n,
        "ranges": ranges,
        "deletes": n,
        "seed": seed,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quick", action="store_true")
    parser.add_argument(
        "--output",
        type=Path,
        help="new report path (default: a unique directory under results/); never overwrites",
    )
    args = parser.parse_args()
    details = {
        "quick": args.quick,
        "note": "timings include validation and reference models",
    }
    with report_run("stress", args.output, Path(__file__), details) as (output, report):
        phases = {
            "exhaustive": lambda: exhaustive(4 if args.quick else 5),
            "random": lambda: random_histories(
                2000 if args.quick else 20000,
                [2, 8, 128] if args.quick else [2, 3, 4, 8, 16, 32, 64, 128, 256],
                [123] if args.quick else [123, 456, 789],
            ),
            "order_matrix": lambda: order_matrix(300 if args.quick else 4000),
            "large": lambda: large(10000 if args.quick else 100000, 200 if args.quick else 5000),
        }
        start = time.perf_counter()
        for name, run in phases.items():
            begin = time.perf_counter()
            result = run()
            result["seconds_including_checks"] = time.perf_counter() - begin
            report[name] = result
            report["status"] = "in_progress"
            write_report(output, report)
            print(name, json.dumps(result), flush=True)
        report["seconds_including_checks"] = time.perf_counter() - start
    print("PASS", output, flush=True)


if __name__ == "__main__":
    main()
