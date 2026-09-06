"""Two explicit equi-join algorithms; duplicate keys preserve every matching pair."""

from collections import defaultdict
from collections.abc import Iterable, Iterator

from ..result import ExecutionStats
from ..schema import Row, Value


def nested_loop_join(left: Iterable[Row], right: Iterable[Row], left_key: int,
                     right_key: int, stats: ExecutionStats | None = None) -> Iterator[Row]:
    stats = stats if stats is not None else ExecutionStats()
    right_rows = list(right)
    for left_row in left:
        for right_row in right_rows:
            stats.join_comparisons += 1
            if left_row[left_key] == right_row[right_key]:
                yield left_row + right_row


def hash_join(left: Iterable[Row], right: Iterable[Row], left_key: int,
              right_key: int, stats: ExecutionStats | None = None) -> Iterator[Row]:
    stats = stats if stats is not None else ExecutionStats()
    buckets: dict[Value, list[Row]] = defaultdict(list)
    for row in right:
        buckets[row[right_key]].append(row)
        stats.hash_build_rows += 1
    for left_row in left:
        stats.hash_probes += 1
        for right_row in buckets.get(left_row[left_key], ()):
            yield left_row + right_row
