"""Immutable syntax nodes with no dependency on database state."""

from dataclasses import dataclass

from ..schema import Column, Value


@dataclass(frozen=True)
class ColumnRef:
    name: str
    table: str | None = None

    def __str__(self):
        return f"{self.table}.{self.name}" if self.table else self.name


@dataclass(frozen=True)
class Literal:
    value: Value


@dataclass(frozen=True)
class Star:
    pass


@dataclass(frozen=True)
class Aggregate:
    function: str
    column: ColumnRef | None  # None represents COUNT(*).

    def __str__(self):
        return f"{self.function}({self.column if self.column else '*'})"


type Operand = ColumnRef | Literal
type SelectItem = ColumnRef | Aggregate | Star


@dataclass(frozen=True)
class Comparison:
    left: Operand
    operator: str
    right: Operand


@dataclass(frozen=True)
class BooleanExpr:
    left: "Condition"
    operator: str
    right: "Condition"


type Condition = Comparison | BooleanExpr


@dataclass(frozen=True)
class Join:
    table: str
    on: Comparison


@dataclass(frozen=True)
class OrderBy:
    expression: ColumnRef | Aggregate
    descending: bool = False


@dataclass(frozen=True)
class Select:
    items: tuple[SelectItem, ...]
    table: str
    joins: tuple[Join, ...] = ()
    where: Condition | None = None
    group_by: tuple[ColumnRef, ...] = ()
    order_by: tuple[OrderBy, ...] = ()


@dataclass(frozen=True)
class CreateTable:
    table: str
    columns: tuple[Column, ...]


@dataclass(frozen=True)
class Insert:
    table: str
    rows: tuple[tuple[Value, ...], ...]


@dataclass(frozen=True)
class CreateIndex:
    name: str
    table: str
    column: str


type Statement = Select | CreateTable | Insert | CreateIndex
