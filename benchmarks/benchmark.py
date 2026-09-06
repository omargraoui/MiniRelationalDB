"""Small end-to-end benchmarks with correctness checks and real perf_counter timings."""

import argparse
from collections import Counter
import csv
from pathlib import Path
import platform
from statistics import median
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from minidb import Column, Database


def measure(function, repeats):
    function()  # Untimed warm-up.
    times = []
    for _ in range(repeats):
        start = perf_counter()
        result = function()
        times.append(perf_counter() - start)
    return median(times), result


def record(kind, left_rows, right_rows, algorithm, seconds, repeats, result):
    return {
        "benchmark": kind, "left_rows": left_rows, "right_rows": right_rows,
        "algorithm": algorithm, "repeats": repeats, "median_seconds": seconds,
        "result_rows": len(result.rows), "rows_scanned": result.stats.rows_scanned,
        "index_used": ";".join(result.stats.indexes_used),
        "join_comparisons": result.stats.join_comparisons,
        "hash_build_rows": result.stats.hash_build_rows, "hash_probes": result.stats.hash_probes,
        "python": platform.python_version(), "platform": platform.platform(),
    }


def search_benchmarks(repeats):
    records = []
    for size in (1_000, 10_000, 50_000):
        database = Database()
        table = database.create_table("items", [Column("id", "INT"), Column("payload", "TEXT")])
        table.insert_many((i, f"item_{i}") for i in range(size))
        start = perf_counter()
        table.create_hash_index("id")
        build_seconds = perf_counter() - start
        print(f"Index construction ({size:,} rows): {build_seconds * 1000:.3f} ms (excluded from lookup timing)")
        sql = f"SELECT payload FROM items WHERE id = {size // 2}"
        baseline = database.execute(sql, use_indexes=False)
        for algorithm, use_indexes in (("full_scan", False), ("hash_index", True)):
            seconds, result = measure(lambda: database.execute(sql, use_indexes=use_indexes), repeats)
            if result.rows != baseline.rows or result.rows != ((f"item_{size // 2}",),):
                raise AssertionError("Search results differ")
            expected_scans = 1 if use_indexes else size
            if result.stats.rows_scanned != expected_scans or bool(result.stats.indexes_used) != use_indexes:
                raise AssertionError("Search did not use the expected access path")
            entry = record("search", size, 0, algorithm, seconds, repeats, result)
            entry["index_build_seconds"] = build_seconds
            records.append(entry)
    return records


def join_benchmarks(repeats):
    records = []
    for left_size, right_size in ((100, 50), (500, 250), (1_000, 500)):
        database = Database()
        left = database.create_table("left_items", [Column("id", "INT"), Column("join_key", "INT")])
        right = database.create_table("right_items", [Column("id", "INT"), Column("join_key", "INT")])
        # Each key occurs twice on the right: exercise duplicate-preserving joins.
        key_count = right_size // 2
        left.insert_many((i, i % key_count) for i in range(left_size))
        right.insert_many((i, i % key_count) for i in range(right_size))
        sql = """SELECT left_items.id, right_items.id FROM left_items
                 INNER JOIN right_items ON left_items.join_key = right_items.join_key"""
        baseline = None
        for algorithm in ("nested_loop", "hash"):
            seconds, result = measure(lambda: database.execute(sql, join_strategy=algorithm), repeats)
            values = Counter(result.rows)
            if baseline is None:
                baseline = values
            if values != baseline or len(result.rows) != left_size * 2:
                raise AssertionError("Join algorithms returned different results")
            entry = record("join", left_size, right_size, algorithm, seconds, repeats, result)
            entry["index_build_seconds"] = ""
            records.append(entry)
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=7)
    parser.add_argument("--output", type=Path, default=ROOT / "benchmarks" / "results.csv")
    args = parser.parse_args()
    if args.repeats < 2:
        parser.error("--repeats must be at least 2")
    print(f"Python {platform.python_version()} | {platform.platform()}")
    records = search_benchmarks(args.repeats) + join_benchmarks(args.repeats)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)
    print("\nbenchmark | left x right | algorithm | median ms | results | base rows scanned")
    for entry in records:
        print(f"{entry['benchmark']:9} | {entry['left_rows']:6} x {entry['right_rows']:<4} | "
              f"{entry['algorithm']:11} | {entry['median_seconds'] * 1000:9.3f} | "
              f"{entry['result_rows']:7} | {entry['rows_scanned']}")
    print(f"\nAll correctness/access-path checks passed. CSV: {args.output}")


if __name__ == "__main__":
    main()
