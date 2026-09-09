import pytest

from minidb.errors import SQLSyntaxError
from minidb.parser import parse, tokenize
from minidb.parser.ast import (
    Aggregate, BooleanExpr, ColumnRef, Comparison, CreateIndex, CreateTable,
    Insert, Literal, Select,
)


def test_tokenizer_kinds_positions_and_escaped_strings():
    tokens = tokenize("select e.name, -1.5e2 FROM employees WHERE name != 'O''Brien'; -- end")
    assert tokens[0].kind == "KEYWORD"
    assert tokens[0].value == "SELECT"
    assert tokens[0].position == 0
    assert tokens[1].kind == "IDENTIFIER"
    assert {token.kind for token in tokens} >= {".", ",", "-", "NUMBER", "OPERATOR", "STRING", ";", "EOF"}
    assert next(token.value for token in tokens if token.kind == "STRING") == "O'Brien"
    assert next(token.value for token in tokens if token.kind == "NUMBER") == 150.0


def test_select_ast_and_boolean_precedence():
    tree = parse("""SELECT department_id, AVG(salary) FROM employees
        WHERE salary >= 70000 AND active = TRUE OR id = 1
        GROUP BY department_id ORDER BY AVG(salary) DESC;""")
    assert isinstance(tree, Select)
    assert tree.items == (ColumnRef("department_id"), Aggregate("AVG", ColumnRef("salary")))
    assert isinstance(tree.where, BooleanExpr)
    assert tree.where.operator == "OR"
    assert tree.where.left.operator == "AND"
    assert tree.where.left.left == Comparison(ColumnRef("salary"), ">=", Literal(70000))
    assert tree.group_by == (ColumnRef("department_id"),)
    assert tree.order_by[0].descending is True


def test_ddl_insert_and_join_ast():
    assert isinstance(parse("CREATE TABLE t (id INT, label TEXT)"), CreateTable)
    assert parse("INSERT INTO t VALUES (-1, 'a'), (+2, 'b')") == Insert("t", ((-1, "a"), (2, "b")))
    assert parse("CREATE INDEX idx ON t (id)") == CreateIndex("idx", "t", "id")
    tree = parse("SELECT a.id FROM a INNER JOIN b ON b.key = a.id")
    assert tree.joins[0].on.left == ColumnRef("key", "b")


@pytest.mark.parametrize("sql", [
    "", "SELECT FROM t", "SELECT * t", "SELECT * FROM t garbage",
    "SELECT * FROM t; SELECT * FROM t", "SELECT * FROM t WHERE id =",
    "SELECT * FROM t WHERE (id = 1", "SELECT SUM(*) FROM t",
    "SELECT * FROM a INNER JOIN b ON a.id > b.id", "INSERT INTO t VALUES ('unclosed)",
    "CREATE TABLE t (id DATE)", "SELECT * FROM t WHERE id = 1e999",
    "SELECT * FROM t WHERE id <> 1", "SELECT * FROM t LIMIT 1",
    "SELECT * FROM t 'WHERE' id = 1", "SELECT name 'FROM' t", "SELECT @ FROM t",
])
def test_invalid_or_unsupported_sql_is_rejected(sql):
    with pytest.raises(SQLSyntaxError):
        parse(sql)


@pytest.mark.parametrize("condition", ["", "id", "id = 1 AND", "id = 1 OR"])
def test_incomplete_where_reports_end_of_input(condition):
    sql = f"SELECT * FROM t WHERE {condition}"
    with pytest.raises(SQLSyntaxError, match=rf"at position {len(sql)}; got ''$"):
        parse(sql)


@pytest.mark.parametrize("sql, diagnostic", [
    ("SELECT t. FROM t", "Expected an identifier"),
    ("SELECT * FROM t GROUP BY", "Expected an identifier"),
    ("SELECT * FROM t ORDER BY", "Expected an identifier"),
    ("INSERT INTO t VALUES (1,)", "Expected a literal"),
])
def test_missing_names_and_list_elements_are_rejected(sql, diagnostic):
    with pytest.raises(SQLSyntaxError, match=diagnostic):
        parse(sql)


@pytest.mark.parametrize("value", ["-TRUE", "+'text'"])
def test_sign_requires_a_numeric_literal(value):
    with pytest.raises(SQLSyntaxError, match="Expected a number after sign"):
        parse(f"INSERT INTO t VALUES ({value})")


def test_keyword_text_and_semicolons_inside_strings_are_data():
    tree = parse("INSERT INTO t VALUES ('WHERE', 'semi; -- still text', 'it''s fine')")
    assert tree.rows == (("WHERE", "semi; -- still text", "it's fine"),)
