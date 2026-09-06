"""Typed schemas and immutable tuple rows; NULL is deliberately unsupported."""

from dataclasses import dataclass
from enum import StrEnum
import math
import re

from .errors import SchemaError, TypeValidationError, UnknownColumnError

type Value = int | float | str | bool
type Row = tuple[Value, ...]


def identifier(name: str) -> str:
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", name):
        raise SchemaError(f"Invalid identifier: {name!r}")
    return name.lower()


class DataType(StrEnum):
    INT = "INT"
    FLOAT = "FLOAT"
    TEXT = "TEXT"
    BOOL = "BOOL"


@dataclass(frozen=True)
class Column:
    name: str
    data_type: DataType | str

    def __post_init__(self):
        object.__setattr__(self, "name", identifier(self.name))
        try:
            object.__setattr__(self, "data_type", DataType(self.data_type.upper()))
        except (ValueError, AttributeError) as exc:
            raise SchemaError(f"Unknown type: {self.data_type!r}") from exc

    def validate(self, value: Value) -> Value:
        match self.data_type:
            case DataType.INT:
                valid = type(value) is int
            case DataType.FLOAT:
                valid = type(value) in (int, float)
                if valid:
                    try:
                        value = float(value)
                        valid = math.isfinite(value)
                    except OverflowError:
                        valid = False
            case DataType.TEXT:
                valid = type(value) is str
            case DataType.BOOL:
                valid = type(value) is bool
        if not valid:
            raise TypeValidationError(
                f"Column {self.name!r} expects {self.data_type}, got {value!r}"
            )
        return value


@dataclass(frozen=True)
class Schema:
    columns: tuple[Column, ...]

    def __post_init__(self):
        object.__setattr__(self, "columns", tuple(self.columns))
        if not self.columns:
            raise SchemaError("A table must have at least one column")
        names = [column.name for column in self.columns]
        if len(set(names)) != len(names):
            raise SchemaError("Duplicate column names")

    def position(self, name: str) -> int:
        name = identifier(name)
        for position, column in enumerate(self.columns):
            if column.name == name:
                return position
        raise UnknownColumnError(f"Unknown column: {name}")

    def validate(self, values) -> Row:
        values = tuple(values)
        if len(values) != len(self.columns):
            raise TypeValidationError(
                f"Expected {len(self.columns)} values, got {len(values)}"
            )
        return tuple(column.validate(value) for column, value in zip(self.columns, values))
