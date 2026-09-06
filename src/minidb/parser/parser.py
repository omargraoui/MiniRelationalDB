"""Recursive descent parser for one deliberately restricted SQL statement."""

from ..errors import SQLSyntaxError
from ..schema import Column
from .ast import (
    Aggregate, BooleanExpr, ColumnRef, Comparison, CreateIndex, CreateTable,
    Insert, Join, Literal, OrderBy, Select, Star, Statement,
)
from .tokenizer import tokenize

AGGREGATES = {"COUNT", "SUM", "AVG", "MIN", "MAX"}


class Parser:
    def __init__(self, sql: str):
        self.tokens = tokenize(sql)
        self.position = 0

    @property
    def current(self):
        return self.tokens[self.position]

    def matches(self, value: str) -> bool:
        # Strings containing keyword text must never act as syntax.
        return self.current.kind not in {"STRING", "NUMBER", "IDENTIFIER"} and self.current.value == value

    def accept(self, value: str) -> bool:
        if self.matches(value):
            self.position += 1
            return True
        return False

    def expect(self, value: str):
        if not self.accept(value):
            self.fail(f"Expected {value!r}")

    def fail(self, message: str):
        raise SQLSyntaxError(f"{message} at position {self.current.position}; got {self.current.value!r}")

    def name(self) -> str:
        if self.current.kind != "IDENTIFIER":
            self.fail("Expected an identifier")
        value = self.current.value
        self.position += 1
        return value

    def column(self) -> ColumnRef:
        first = self.name()
        if self.accept("."):
            return ColumnRef(self.name(), first)
        return ColumnRef(first)

    def literal(self) -> Literal:
        sign = 1
        signed = False
        if self.accept("-"):
            sign, signed = -1, True
        elif self.accept("+"):
            signed = True
        token = self.current
        if token.kind == "NUMBER":
            self.position += 1
            return Literal(sign * token.value)
        if signed:
            self.fail("Expected a number after sign")
        if token.kind == "STRING":
            self.position += 1
            return Literal(token.value)
        if self.accept("TRUE"):
            return Literal(True)
        if self.accept("FALSE"):
            return Literal(False)
        self.fail("Expected a literal")

    def operand(self):
        return self.column() if self.current.kind == "IDENTIFIER" else self.literal()

    def expression(self):
        if self.current.kind == "KEYWORD" and self.current.value in AGGREGATES:
            function = self.current.value
            self.position += 1
            self.expect("(")
            if self.accept("*"):
                if function != "COUNT":
                    self.fail("Only COUNT supports *")
                column = None
            else:
                column = self.column()
            self.expect(")")
            return Aggregate(function, column)
        return self.column()

    def comparison(self) -> Comparison:
        left = self.operand()
        if self.current.kind != "OPERATOR":
            self.fail("Expected a comparison operator")
        operator = self.current.value
        self.position += 1
        return Comparison(left, operator, self.operand())

    def condition_atom(self):
        if self.accept("("):
            condition = self.condition()
            self.expect(")")
            return condition
        return self.comparison()

    def conjunction(self):
        left = self.condition_atom()
        while self.accept("AND"):
            left = BooleanExpr(left, "AND", self.condition_atom())
        return left

    def condition(self):
        left = self.conjunction()
        while self.accept("OR"):
            left = BooleanExpr(left, "OR", self.conjunction())
        return left

    def select(self) -> Select:
        items = [Star() if self.accept("*") else self.expression()]
        while self.accept(","):
            items.append(Star() if self.accept("*") else self.expression())
        self.expect("FROM")
        table = self.name()
        joins = []
        while self.accept("INNER"):
            self.expect("JOIN")
            joined_table = self.name()
            self.expect("ON")
            on = self.comparison()
            if on.operator != "=" or not isinstance(on.left, ColumnRef) or not isinstance(on.right, ColumnRef):
                self.fail("INNER JOIN requires column = column")
            joins.append(Join(joined_table, on))
        where = self.condition() if self.accept("WHERE") else None
        groups = []
        if self.accept("GROUP"):
            self.expect("BY")
            groups.append(self.column())
            while self.accept(","):
                groups.append(self.column())
        order = []
        if self.accept("ORDER"):
            self.expect("BY")
            while True:
                expression = self.expression()
                descending = self.accept("DESC")
                if not descending:
                    self.accept("ASC")
                order.append(OrderBy(expression, descending))
                if not self.accept(","):
                    break
        return Select(tuple(items), table, tuple(joins), where, tuple(groups), tuple(order))

    def create(self):
        if self.accept("TABLE"):
            table = self.name()
            self.expect("(")
            columns = []
            while True:
                name = self.name()
                if self.current.kind != "KEYWORD" or self.current.value not in {"INT", "FLOAT", "TEXT", "BOOL"}:
                    self.fail("Expected INT, FLOAT, TEXT, or BOOL")
                data_type = self.current.value
                self.position += 1
                columns.append(Column(name, data_type))
                if not self.accept(","):
                    break
            self.expect(")")
            return CreateTable(table, tuple(columns))
        self.expect("INDEX")
        name = self.name()
        self.expect("ON")
        table = self.name()
        self.expect("(")
        column = self.name()
        self.expect(")")
        return CreateIndex(name, table, column)

    def insert(self) -> Insert:
        self.expect("INTO")
        table = self.name()
        self.expect("VALUES")
        rows = []
        while True:
            self.expect("(")
            values = [self.literal().value]
            while self.accept(","):
                values.append(self.literal().value)
            self.expect(")")
            rows.append(tuple(values))
            if not self.accept(","):
                break
        return Insert(table, tuple(rows))

    def parse(self) -> Statement:
        if self.accept("SELECT"):
            statement = self.select()
        elif self.accept("CREATE"):
            statement = self.create()
        elif self.accept("INSERT"):
            statement = self.insert()
        else:
            self.fail("Expected SELECT, CREATE, or INSERT")
        self.accept(";")
        if self.current.kind != "EOF":
            self.fail("Unexpected trailing tokens")
        return statement


def parse(sql: str) -> Statement:
    return Parser(sql).parse()
