from collections.abc import Iterable, Iterator, Mapping
from types import MappingProxyType

from .errors import IndexExistsError
from .indexes import HashIndex
from .schema import Row, Schema, Value, identifier


class Table:
    def __init__(self, name: str, schema: Schema):
        self._name = identifier(name)
        self._schema = schema
        self._rows: list[Row] = []
        self._indexes: dict[str, HashIndex] = {}

    @property
    def name(self) -> str:
        return self._name

    @property
    def schema(self) -> Schema:
        return self._schema

    @property
    def columns(self):
        return self.schema.columns

    @property
    def rows(self) -> tuple[Row, ...]:
        return tuple(self._rows)

    @property
    def indexes(self) -> Mapping[str, HashIndex]:
        return MappingProxyType(self._indexes)

    def __len__(self) -> int:
        return len(self._rows)

    def iter_rows(self, row_ids: Iterable[int] | None = None) -> Iterator[Row]:
        if row_ids is None:
            yield from self._rows
        else:
            for row_id in row_ids:
                yield self._rows[row_id]

    def insert(self, values: Iterable[Value]) -> int:
        return self.insert_many([values])[0]

    def insert_many(self, rows: Iterable[Iterable[Value]]) -> list[int]:
        # Validate the whole batch before changing either rows or indexes.
        validated = [self.schema.validate(row) for row in rows]
        positions = [(self.schema.position(name), index) for name, index in self._indexes.items()]
        row_ids = []
        for row in validated:
            row_id = len(self._rows)
            self._rows.append(row)
            for position, index in positions:
                index._add(row[position], row_id)
            row_ids.append(row_id)
        return row_ids

    def create_hash_index(self, column: str, *, name: str | None = None) -> HashIndex:
        position = self.schema.position(column)
        column = self.columns[position].name
        if column in self._indexes:
            raise IndexExistsError(f"Index already exists on {self.name}.{column}")
        index = HashIndex(column, identifier(name) if name else f"{self.name}.{column}")
        for row_id, row in enumerate(self._rows):
            index._add(row[position], row_id)
        self._indexes[column] = index
        return index
