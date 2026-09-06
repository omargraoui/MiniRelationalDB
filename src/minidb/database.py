from collections.abc import Iterable, Mapping
from types import MappingProxyType

from .errors import IndexExistsError, TableExistsError, UnknownTableError
from .execution import Executor
from .parser import parse
from .schema import Column, Schema, identifier
from .table import Table


class Database:
    def __init__(self):
        self._tables: dict[str, Table] = {}
        self._executor = Executor(self)

    @property
    def tables(self) -> Mapping[str, Table]:
        return MappingProxyType(self._tables)

    def create_table(self, name: str, columns: Schema | Iterable[Column]) -> Table:
        name = identifier(name)
        if name in self._tables:
            raise TableExistsError(f"Table already exists: {name}")
        schema = columns if isinstance(columns, Schema) else Schema(tuple(columns))
        table = Table(name, schema)
        self._tables[name] = table
        return table

    def get_table(self, name: str) -> Table:
        name = identifier(name)
        try:
            return self._tables[name]
        except KeyError as exc:
            raise UnknownTableError(f"Unknown table: {name}") from exc

    def create_index(self, name: str, table: str, column: str):
        name = identifier(name)
        target = self.get_table(table)
        if any(index.name == name for existing in self._tables.values() for index in existing.indexes.values()):
            raise IndexExistsError(f"Index name already exists: {name}")
        return target.create_hash_index(column, name=name)

    def execute(self, sql: str, *, join_strategy: str = "hash", use_indexes: bool = True):
        return self._executor.execute(parse(sql), join_strategy=join_strategy, use_indexes=use_indexes)
