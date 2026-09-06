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
