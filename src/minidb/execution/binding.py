"""Resolve names and check operand types before reading data, even for empty tables."""

from dataclasses import dataclass

from ..errors import AmbiguousColumnError, TypeValidationError, UnknownColumnError
from ..parser.ast import ColumnRef, Literal
from ..schema import DataType, Row, Value


@dataclass(frozen=True)
class BoundColumn:
    position: int
    table: str
    name: str
    data_type: DataType

    def read(self, row: Row) -> Value:
        return row[self.position]


class Scope:
    def __init__(self, columns: list[BoundColumn]):
        self.columns = columns

    @classmethod
    def from_table(cls, table, offset: int = 0):
        return cls([BoundColumn(offset + i, table.name, column.name, column.data_type)
                    for i, column in enumerate(table.columns)])

    def resolve(self, ref: ColumnRef) -> BoundColumn:
        matches = [column for column in self.columns
                   if column.name == ref.name and (ref.table is None or column.table == ref.table)]
        if not matches:
            raise UnknownColumnError(f"Unknown column: {ref}")
        if len(matches) > 1:
            raise AmbiguousColumnError(f"Ambiguous column: {ref}; qualify it with a table name")
        return matches[0]

    def bind_operand(self, operand):
        return self.resolve(operand) if isinstance(operand, ColumnRef) else operand


def operand_type(operand: BoundColumn | Literal) -> DataType:
    if isinstance(operand, BoundColumn):
        return operand.data_type
    return {int: DataType.INT, float: DataType.FLOAT, str: DataType.TEXT, bool: DataType.BOOL}[type(operand.value)]


def validate_comparable(left, right) -> None:
    left_type, right_type = operand_type(left), operand_type(right)
    numeric = {DataType.INT, DataType.FLOAT}
    if left_type != right_type and not {left_type, right_type} <= numeric:
        raise TypeValidationError(f"Cannot compare {left_type} with {right_type}")


def read_operand(operand, row: Row):
    return operand.read(row) if isinstance(operand, BoundColumn) else operand.value
