# Recorded local benchmark

Run on 2026-09-06 with Python 3.13.5, Windows-11-10.0.26200-SP0, using:

```console
python benchmarks/benchmark.py
```

The values below are actual median elapsed times from seven repetitions after
one untimed warm-up per algorithm. They measure full query execution, including
parsing, binding, counters, and materialization. Index construction and data
generation are excluded; temporary hash-join construction is included.

## Equality search

Each query returns exactly one row. The scan reads every input row; indexed
access fetches exactly one candidate row. Results and access counters were checked.

| Input rows | Full scan (ms) | Hash index (ms) | Index build, one shot (ms) |
| ---: | ---: | ---: | ---: |
| 1,000 | 0.382 | 0.041 | 0.221 |
| 10,000 | 3.106 | 0.042 | 2.599 |
| 50,000 | 15.816 | 0.041 | 14.051 |

## Inner equi-join

Right-side join keys occur twice. Both algorithms returned identical multisets.
Base rows fetched equal the sum of input sizes; repeated nested-loop comparisons
are counted separately.

| Left x right rows | Output rows | Nested loop (ms) | Hash join (ms) | Nested comparisons | Hash build / probes |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 100 x 50 | 200 | 0.731 | 0.259 | 5,000 | 50 / 100 |
| 500 x 250 | 1,000 | 12.377 | 1.042 | 125,000 | 250 / 500 |
| 1,000 x 500 | 2,000 | 47.964 | 2.225 | 500,000 | 500 / 1,000 |

Raw values and environment metadata were saved to `benchmarks/results.csv`.
That generated file is ignored by Git; rerunning the script replaces it. This
document retains the recorded snapshot. Timings vary between runs, particularly
for short indexed queries; these measurements do not establish a universal
speedup or production workload performance.

## Selective index choice (2026-09-13)

Run with Python 3.13.5 on Windows-11-10.0.26200-SP0 using
`python benchmarks/benchmark.py` (seven repetitions after one warm-up).
Each table has unique IDs and two equally sized categories. The query selects
the middle ID and its category, returning exactly one row.

The category-only baseline reproduces the previous first-index access path.
After adding the ID index outside timing, the engine selects it for both orders
of the `AND` predicate. This compares access paths in the current engine, not
separate historical builds. All results were checked against a forced full scan;
chosen indexes and exact row-read counts were also verified.

| Input rows | Category only (ms) | Both indexes, category first (ms) | Both indexes, ID first (ms) | Rows read, baseline / selective |
| ---: | ---: | ---: | ---: | ---: |
| 1,000 | 0.414 | 0.060 | 0.057 | 500 / 1 |
| 10,000 | 3.598 | 0.063 | 0.063 | 5,000 / 1 |
| 50,000 | 19.521 | 0.057 | 0.056 | 25,000 / 1 |

Timings include parsing, index selection, residual filtering, and materialization.
Index construction and data insertion are excluded. Local timings are noisy;
the deterministic improvement is reading one candidate instead of half the table.
The search and join benchmarks also passed their correctness/access-path checks.

## Index intersection for AND predicates (2026-09-19)

Run with Python 3.13.5 on Windows-11-10.0.26200-SP0 using
`python benchmarks/benchmark.py` (seven repetitions after one warm-up).
Each table has two columns, `region` and `tier`, independently partitioning rows
into 10 equally selective groups (10% of rows each); their true joint match is
10x smaller than either bucket alone. The region-only baseline reproduces the
previous single-index access path (the most-selective-index choice added in the
prior commit, which has no way to combine two indexes). After adding a `tier`
index outside timing, the engine intersects both for the same `AND` predicate.

| Input rows | Region only (ms) | Region + tier intersected (ms) | Rows scanned, single / intersected |
| ---: | ---: | ---: | ---: |
| 1,000 | 0.118 | 0.076 | 100 / 10 |
| 10,000 | 0.688 | 0.239 | 1,000 / 100 |
| 50,000 | 3.904 | 1.720 | 5,000 / 500 |

Rows scanned drop by exactly 10x at every size, matching the constructed
selectivity of the two independent partitions; this is a deterministic property
of the access path, not a timing artifact. Wall-clock time also improved at every
size in this run, but short in-memory timings are noisy and depend on hardware
and system activity. A regression test (`test_index_intersection_never_probes_a_bucket_larger_than_the_candidates_assembled`)
confirms the engine still never copies a bucket larger than the candidate set
already assembled, so a highly selective single index (e.g. a unique key) is
never penalized by intersecting against a much broader one. The search, join,
and selectivity benchmarks also passed their correctness/access-path checks.
