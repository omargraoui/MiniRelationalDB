"""Bind -> scan/index -> join -> filter -> group -> project/sort -> result."""

from ..errors import QueryError
from ..parser.ast import Aggregate, CreateIndex, CreateTable, Insert, Select, Star
from ..result import ExecutionStats, QueryResult
from .aggregation import BoundAggregate, bind_aggregate, group_rows
from .binding import BoundColumn, Scope, validate_comparable
from .filtering import bind_condition, equality_candidates
from .joins import hash_join, nested_loop_join


class Executor:
    def __init__(self, database):
        self.database = database

    def execute(self, statement, *, join_strategy: str = "hash", use_indexes: bool = True) -> QueryResult:
        if join_strategy not in {"hash", "nested_loop"}:
            raise QueryError(f"Unknown join strategy: {join_strategy!r}")
        if isinstance(statement, CreateTable):
            table = self.database.create_table(statement.table, statement.columns)
            return QueryResult(message=f"Created table {table.name}")
        if isinstance(statement, Insert):
            table = self.database.get_table(statement.table)
            count = len(table.insert_many(statement.rows))
            return QueryResult(affected_rows=count, message=f"Inserted {count} rows into {table.name}")
        if isinstance(statement, CreateIndex):
            self.database.create_index(statement.name, statement.table, statement.column)
            return QueryResult(message=f"Created hash index {statement.name}")
        if not isinstance(statement, Select):
            raise QueryError(f"Unsupported statement: {type(statement).__name__}")
        return self.select(statement, join_strategy, use_indexes)

    @staticmethod
    def scan(table, stats, row_ids=None):
        for row in table.iter_rows(row_ids):
            stats.rows_scanned += 1
            yield row

    def select(self, statement: Select, join_strategy: str, use_indexes: bool):
        table = self.database.get_table(statement.table)
        scope = Scope.from_table(table)
        seen_tables = {table.name}
        join_plans = []
        for join in statement.joins:
            right = self.database.get_table(join.table)
            if right.name in seen_tables:
                raise QueryError("Repeated tables/self-joins require aliases, which are unsupported")
            seen_tables.add(right.name)
            offset = len(scope.columns)
            scope = Scope(scope.columns + Scope.from_table(right, offset).columns)
            left_key = scope.resolve(join.on.left)
            right_key = scope.resolve(join.on.right)
            if left_key.position >= offset:
                left_key, right_key = right_key, left_key
            if left_key.position >= offset or right_key.position < offset:
                raise QueryError("JOIN must connect the new table to a preceding table")
            validate_comparable(left_key, right_key)
            join_plans.append((right, left_key.position, right_key.position - offset))

        condition = bind_condition(statement.where, scope) if statement.where else None
        groups = [scope.resolve(column) for column in statement.group_by]

        def bind(expression):
            return bind_aggregate(expression, scope) if isinstance(expression, Aggregate) else scope.resolve(expression)

        columns, selections = [], []
        for item in statement.items:
            if isinstance(item, Star):
                if len(statement.items) != 1:
                    raise QueryError("SELECT * must be the only select item")
                selections.extend(scope.columns)
                columns.extend(f"{column.table}.{column.name}" if join_plans else column.name
                               for column in scope.columns)
            else:
                columns.append(str(item))
                selections.append(bind(item))
        orders = [bind(order.expression) for order in statement.order_by]
        grouped = bool(groups) or any(isinstance(item, BoundAggregate) for item in selections + orders)
        if grouped:
            if any(isinstance(item, Star) for item in statement.items):
                raise QueryError("SELECT * is unsupported with grouping/aggregation")
            for item in selections + orders:
                if isinstance(item, BoundColumn) and item not in groups:
                    raise QueryError(f"Column {item.table}.{item.name} must appear in GROUP BY")

        stats = ExecutionStats(join_strategy=join_strategy if join_plans else None)
        row_ids = None
        if use_indexes and not join_plans and condition:
            for column, value in equality_candidates(condition):
                if column.name in table.indexes:
                    row_ids = table.indexes[column.name].lookup(value)
                    stats.indexes_used.append(f"{table.name}.{column.name}")
                    break
        rows = self.scan(table, stats, row_ids)
        join_function = hash_join if join_strategy == "hash" else nested_loop_join
        for right, left_key, right_key in join_plans:
            rows = join_function(rows, self.scan(right, stats), left_key, right_key, stats)
        filtered = [row for row in rows if condition is None or condition.evaluate(row)]

        # Each record carries sort values separately, allowing ORDER BY an unselected column.
        records = []
        if grouped:
            for members in group_rows(filtered, groups).values():
                cache = {}

                def evaluate(item):
                    if item not in cache:
                        cache[item] = item.evaluate(members) if isinstance(item, BoundAggregate) else item.read(members[0])
                    return cache[item]

                records.append((tuple(evaluate(item) for item in selections),
                                tuple(evaluate(item) for item in orders)))
        else:
            records = [(tuple(item.read(row) for item in selections),
                        tuple(item.read(row) for item in orders)) for row in filtered]
        # Stable sorts from the last key implement mixed ASC/DESC directions.
        for i in reversed(range(len(orders))):
            records.sort(key=lambda record: (record[1][i] is None, record[1][i]),
                         reverse=statement.order_by[i].descending)
        return QueryResult(tuple(columns), tuple(record[0] for record in records), stats)
