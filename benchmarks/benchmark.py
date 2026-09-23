"""Deterministic timings for the selected installed ordered_btree library.

Reports raw samples and medians. Inputs/reference expectations are prepared
outside timed regions. Times include API safety checks, not model validation.
"""

from __future__ import annotations

import argparse
import gc
import random
import statistics
import sys
import time
from pathlib import Path

# Resolve shared tool support, never src: use the caller's selected installation.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ordered_btree import BTree
from tools._reports import report_run, write_report


def elapsed_ms(call):
    start = time.perf_counter_ns()
    result = call()
    return result, (time.perf_counter_ns() - start) / 1_000_000


def structure_bytes(tree):
    work, total = [tree._root], 0
    while work:
        node = work.pop()
        total += sys.getsizeof(node) + sys.getsizeof(node.keys) + sys.getsizeof(node.children)
        work.extend(node.children)
    # Excludes key objects, allocator metadata, temporary and peak allocations.
    return total + sys.getsizeof(tree)


def run_case(cls, degree, insertion, probes, deletion, ranges, repeats):
    expected = list(range(len(insertion)))
    expected_probes = [0 <= key < len(insertion) for key in probes]
    expected_ranges = [list(range(max(0, lo), min(len(insertion), hi))) for lo, hi in ranges]
    samples = []
    structure = None
    for _ in range(repeats):
        gc.collect()
        tree = cls(t=degree)

        def insert_all(tree=tree):
            for key in insertion:
                tree.insert(key)

        _, ins = elapsed_ms(insert_all)
        assert list(tree) == expected
        tree.validate()
        structure = structure_bytes(tree)
        found, lookup = elapsed_ms(lambda tree=tree: sum(key in tree for key in probes))
        assert found == sum(expected_probes)
        for key, expected_hit in zip(probes, expected_probes, strict=True):
            actual_hit = key in tree
            assert actual_hit == expected_hit, f"incorrect membership for {key}"
        values, scan = elapsed_ms(lambda tree=tree: list(tree))
        assert values == expected
        ranged, span = elapsed_ms(
            lambda tree=tree: sum(len(list(tree.range(lo, hi))) for lo, hi in ranges)
        )
        assert ranged == sum(map(len, expected_ranges))
        for (lo, hi), expected_values in zip(ranges, expected_ranges, strict=True):
            actual_values = list(tree.range(lo, hi))
            assert actual_values == expected_values, f"incorrect range [{lo}, {hi})"
        _, representation = elapsed_ms(lambda tree=tree: repr(tree))

        def delete_all(tree=tree):
            for key in deletion:
                tree.delete(key)

        _, deletion_ms = elapsed_ms(delete_all)
        assert len(tree) == 0
        tree.validate()
        samples.append(
            {
                "insert_ms": ins,
                "search_ms": lookup,
                "iterate_ms": scan,
                "ranges_ms": span,
                "repr_ms": representation,
                "delete_ms": deletion_ms,
            }
        )
    return {
        "degree": degree,
        "structure_bytes_excluding_keys": structure,
        "median_ms": {name: statistics.median(s[name] for s in samples) for name in samples[0]},
        "samples": samples,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=100000)
    parser.add_argument("--probes", type=int, default=50000)
    parser.add_argument("--ranges", type=int, default=5000)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--degrees", type=int, nargs="+", default=[2, 8, 32, 128, 512])
    parser.add_argument(
        "--output",
        type=Path,
        help="new report path (default: a unique directory under results/); never overwrites",
    )
    args = parser.parse_args()
    if min(args.n, args.probes, args.ranges, args.repeats) <= 0 or min(args.degrees) < 2:
        parser.error("sizes/repetitions must be positive; degrees must be >= 2")
    details = {
        "n": args.n,
        "probes": args.probes,
        "ranges": args.ranges,
        "range_width": 10,
        "range_start_region": "upper 10%",
        "repeats": args.repeats,
        "seed": 34789,
        "gc": "enabled; collected before each repetition",
        "note": "Timings include API checks; validation/model work excluded.",
        "cases": [],
    }
    with report_run("benchmark", args.output, Path(__file__), details) as (output, report):
        rng = random.Random(34789)
        insertion = list(range(args.n))
        rng.shuffle(insertion)
        deletion = insertion.copy()
        rng.shuffle(deletion)
        probes = [rng.randrange(2 * args.n) for _ in range(args.probes)]
        starts = [rng.randrange(max(0, args.n * 9 // 10), args.n) for _ in range(args.ranges)]
        ranges = [(start, start + 10) for start in starts]
        for degree in args.degrees:
            result = run_case(BTree, degree, insertion, probes, deletion, ranges, args.repeats)
            result["implementation"] = "ordered_btree"
            report["cases"].append(result)
            report["status"] = "in_progress"
            write_report(output, report)
            print("ordered_btree", degree, result["median_ms"], flush=True)
    print("PASS", output, flush=True)


if __name__ == "__main__":
    main()
