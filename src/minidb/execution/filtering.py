import operator
from dataclasses import dataclass

from ..parser.ast import BooleanExpr, Literal
from .binding import BoundColumn, Scope, read_operand, validate_comparable

OPERATORS = {"=": operator.eq, "!=": operator.ne, "<": operator.lt,
             "<=": operator.le, ">": operator.gt, ">=": operator.ge}


@dataclass(frozen=True)
class BoundComparison:
    left: BoundColumn | Literal
    operator: str
    right: BoundColumn | Literal

    def evaluate(self, row) -> bool:
        return OPERATORS[self.operator](read_operand(self.left, row), read_operand(self.right, row))


@dataclass(frozen=True)
class BoundBoolean:
    left: "BoundCondition"
    operator: str
    right: "BoundCondition"

    def evaluate(self, row) -> bool:
        if self.operator == "AND":
            return self.left.evaluate(row) and self.right.evaluate(row)
        return self.left.evaluate(row) or self.right.evaluate(row)


type BoundCondition = BoundComparison | BoundBoolean


def bind_condition(condition, scope: Scope) -> BoundCondition:
    if isinstance(condition, BooleanExpr):
        return BoundBoolean(bind_condition(condition.left, scope), condition.operator,
                            bind_condition(condition.right, scope))
    left = scope.bind_operand(condition.left)
    right = scope.bind_operand(condition.right)
    validate_comparable(left, right)
    return BoundComparison(left, condition.operator, right)


def equality_candidates(condition: BoundCondition):
    """Only mandatory equalities are safe: never extract a branch from OR."""
    if isinstance(condition, BoundBoolean):
        if condition.operator == "AND":
            yield from equality_candidates(condition.left)
            yield from equality_candidates(condition.right)
    elif condition.operator == "=":
        if isinstance(condition.left, BoundColumn) and isinstance(condition.right, Literal):
            yield condition.left, condition.right.value
        elif isinstance(condition.right, BoundColumn) and isinstance(condition.left, Literal):
            yield condition.right, condition.left.value
