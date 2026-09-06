"""Equality buckets map typed values to stable, append-only row IDs."""

from collections import defaultdict

from ..schema import Value


class HashIndex:
    def __init__(self, column: str, name: str):
        self.column = column
        self.name = name
        self._buckets: dict[Value, list[int]] = defaultdict(list)

    def _add(self, value: Value, row_id: int) -> None:
        self._buckets[value].append(row_id)

    def lookup(self, value: Value) -> tuple[int, ...]:
        """Return matching row IDs without exposing mutable buckets."""
        return tuple(self._buckets.get(value, ()))
