"""Manual grouping and aggregates over Python rows."""

from dataclasses import dataclass
import math

from ..errors import QueryError, TypeValidationError
from ..parser.ast import Aggregate
from ..schema import DataType
from .binding import BoundColumn, Scope


@dataclass(frozen=True)
class BoundAggregate:
    function: str
    column: BoundColumn | None

    def evaluate(self, rows):
        count = 0
        total = 0
        smallest = largest = None
        for row in rows:
            count += 1
            if self.function == "COUNT":
                continue
            value = self.column.read(row)
            if self.function in {"SUM", "AVG"}:
                total += value
                if isinstance(total, float) and not math.isfinite(total):
                    raise QueryError(f"{self.function} intermediate sum exceeds floating-point range")
            elif self.function == "MIN":
                if smallest is None or value < smallest:
                    smallest = value
            elif self.function == "MAX":
                if largest is None or value > largest:
                    largest = value
        if self.function == "COUNT":
            return count
        if not count:
            return None
        if self.function == "SUM":
            return total
        if self.function == "AVG":
            try:
                return total / count
            except OverflowError as exc:
                raise QueryError("AVG result exceeds floating-point range") from exc
        return smallest if self.function == "MIN" else largest


def bind_aggregate(expression: Aggregate, scope: Scope) -> BoundAggregate:
    column = scope.resolve(expression.column) if expression.column else None
    if expression.function in {"SUM", "AVG"} and column.data_type not in {DataType.INT, DataType.FLOAT}:
        raise TypeValidationError(f"{expression.function} requires INT or FLOAT")
    return BoundAggregate(expression.function, column)


def group_rows(rows, columns: list[BoundColumn]):
    if not columns:
        # Global aggregates produce one row, including on empty input.
        return {(): rows}
    groups = {}
    for row in rows:
        key = tuple(column.read(row) for column in columns)
        groups.setdefault(key, []).append(row)
    return groups
