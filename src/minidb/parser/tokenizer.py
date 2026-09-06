"""A small lexer: explicit tokens, positions, SQL quotes, and no SQL library."""

from dataclasses import dataclass
import math
import re

from ..errors import SQLSyntaxError

KEYWORDS = frozenset("""
SELECT FROM WHERE ORDER BY GROUP INNER JOIN ON CREATE TABLE INSERT INTO VALUES
INDEX ASC DESC AND OR COUNT SUM AVG MIN MAX INT FLOAT TEXT BOOL TRUE FALSE
""".split())

_TOKEN = re.compile(
    r"(?P<SPACE>\s+)|(?P<COMMENT>--[^\n]*)"
    r"|(?P<STRING>'(?:[^']|'')*')"
    r"|(?P<NUMBER>(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)"
    r"|(?P<IDENTIFIER>[A-Za-z_][A-Za-z_0-9]*)"
    r"|(?P<OPERATOR>!=|<=|>=|=|<|>)"
    r"|(?P<PUNCTUATION>[,();.*+-])"
)


@dataclass(frozen=True)
class Token:
    kind: str
    value: str | int | float
    position: int


def tokenize(sql: str) -> list[Token]:
    tokens = []
    position = 0
    while position < len(sql):
        match = _TOKEN.match(sql, position)
        if match is None:
            raise SQLSyntaxError(f"Unexpected character {sql[position]!r} at position {position}")
        kind, raw = match.lastgroup, match.group()
        value = raw
        if kind == "STRING":
            value = raw[1:-1].replace("''", "'")
        elif kind == "NUMBER":
            try:
                value = float(raw) if any(char in raw.lower() for char in ".e") else int(raw)
            except ValueError as exc:
                raise SQLSyntaxError(f"Invalid number at position {position}") from exc
            if isinstance(value, float) and not math.isfinite(value):
                raise SQLSyntaxError(f"Non-finite number at position {position}")
        elif kind == "IDENTIFIER":
            if raw.upper() in KEYWORDS:
                kind, value = "KEYWORD", raw.upper()
            else:
                value = raw.lower()
        elif kind == "PUNCTUATION":
            kind = raw
        if kind not in ("SPACE", "COMMENT"):
            tokens.append(Token(kind, value, position))
        position = match.end()
    tokens.append(Token("EOF", "", len(sql)))
    return tokens
