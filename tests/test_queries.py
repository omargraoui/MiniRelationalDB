import pytest

from minidb import Database
from minidb.errors import QueryError, TypeValidationError, UnknownColumnError, UnknownTableError


def test_select_star_projection_and_result_format(db):
    result = db.execute("SELECT * FROM employees")
    assert result.columns == ("id", "name", "department_id", "salary", "active")
    assert result.rows[0] == (1, "Alice", 10, 90000.0, True)
    assert len(result.rows) == 5
    projection = db.execute("SELECT name, salary FROM employees WHERE id = 1")
    assert projection.rows == (("Alice", 90000.0),)
    assert "| name" in str(projection) and "Alice" in str(projection)
    assert "(1 rows)" in str(projection)


@pytest.mark.parametrize("operator,value,expected", [
    ("=", 3, (3,)), ("!=", 3, (1, 2, 4, 5)), ("<", 3, (1, 2)),
    ("<=", 3, (1, 2, 3)), (">", 3, (4, 5)), (">=", 3, (3, 4, 5)),
])
def test_where_comparison_operators(db, operator, value, expected):
    result = db.execute(f"SELECT id FROM employees WHERE id {operator} {value}")
    assert result.rows == tuple((i,) for i in expected)


def test_and_or_parentheses_and_column_comparisons(db):
    assert db.execute("SELECT id FROM employees WHERE salary > 60000 AND active = TRUE").rows == ((1,), (3,), (4,))
    assert db.execute("SELECT id FROM employees WHERE id = 1 OR id = 2 AND active = TRUE").rows == ((1,),)
    assert db.execute("SELECT id FROM employees WHERE (id = 1 OR id = 2) AND active = FALSE").rows == ((2,),)
    assert len(db.execute("SELECT id FROM employees WHERE id < department_id").rows) == 5
    assert db.execute("SELECT id FROM employees WHERE name = 'Alice'").rows == ((1,),)


def test_ordering_default_asc_desc_and_multiple_keys(db):
    assert db.execute("SELECT id FROM employees ORDER BY salary").rows == ((5,), (2,), (4,), (3,), (1,))
    assert db.execute("SELECT id FROM employees ORDER BY salary ASC").rows == ((5,), (2,), (4,), (3,), (1,))
    assert db.execute("SELECT id FROM employees ORDER BY salary DESC").rows == ((1,), (3,), (4,), (2,), (5,))
    assert db.execute("SELECT id FROM employees ORDER BY department_id ASC, salary DESC").rows == ((1,), (3,), (4,), (2,), (5,))


def test_grouping_and_all_aggregates(db):
    result = db.execute("""SELECT department_id, COUNT(*), COUNT(salary), SUM(salary),
        AVG(salary), MIN(salary), MAX(salary) FROM employees
        GROUP BY department_id ORDER BY department_id""")
    assert result.rows == (
        (10, 2, 2, 170000.0, 85000.0, 80000.0, 90000.0),
        (20, 2, 2, 130000.0, 65000.0, 60000.0, 70000.0),
        (30, 1, 1, 50000.0, 50000.0, 50000.0, 50000.0),
    )
    assert db.execute("SELECT COUNT(*), SUM(salary), AVG(salary), MIN(name), MAX(name) FROM employees").rows == (
        (5, 350000.0, 70000.0, "Alice", "Emma"),
    )


def test_where_before_grouping_and_order_by_unselected_aggregate(db):
    result = db.execute("""SELECT department_id, COUNT(*) FROM employees WHERE active = TRUE
        GROUP BY department_id ORDER BY AVG(salary) DESC""")
    assert result.rows == ((10, 2), (20, 1))
    assert db.execute("SELECT department_id FROM employees GROUP BY department_id").rows == ((10,), (20,), (30,))
    assert db.execute("SELECT department_id, active, COUNT(*) FROM employees GROUP BY department_id, active").rows == (
        (10, True, 2), (20, False, 1), (20, True, 1), (30, False, 1),
    )


def test_empty_tables_and_empty_aggregates():
    db = Database()
    db.execute("CREATE TABLE empty (id INT, category TEXT)")
    result = db.execute("SELECT * FROM empty ORDER BY id")
    assert result.rows == () and "(0 rows)" in str(result)
    result = db.execute("SELECT COUNT(*), COUNT(id), SUM(id), AVG(id), MIN(id), MAX(id) FROM empty")
    assert result.rows == ((0, 0, None, None, None, None),)
    assert "NULL" in str(result)
    assert db.execute("SELECT category, COUNT(*) FROM empty GROUP BY category").rows == ()


@pytest.mark.parametrize("sql", [
    "SELECT missing FROM empty", "SELECT id FROM empty WHERE missing = 1",
    "SELECT id FROM empty ORDER BY missing", "SELECT COUNT(missing) FROM empty",
    "SELECT COUNT(*) FROM empty GROUP BY missing", "SELECT other.id FROM empty",
])
def test_unknown_columns_rejected_even_on_empty_input(sql):
    db = Database()
    db.execute("CREATE TABLE empty (id INT)")
    with pytest.raises(UnknownColumnError):
        db.execute(sql)


def test_semantic_errors(db):
    with pytest.raises(UnknownTableError):
        db.execute("SELECT * FROM missing")
    for sql in ("SELECT name, COUNT(*) FROM employees", "SELECT name FROM employees GROUP BY department_id",
                "SELECT * FROM employees GROUP BY id", "SELECT *, id FROM employees",
                "SELECT COUNT(*) FROM employees ORDER BY name"):
        with pytest.raises(QueryError):
            db.execute(sql)
    for sql in ("SELECT SUM(name) FROM employees", "SELECT AVG(active) FROM employees",
                "SELECT id FROM employees WHERE id = TRUE", "SELECT id FROM employees WHERE salary > 'high'"):
        with pytest.raises(TypeValidationError):
            db.execute(sql)
    with pytest.raises(QueryError):
        db.execute("SELECT * FROM employees", join_strategy="magic")


def test_numeric_aggregate_overflow_is_a_database_error():
    db = Database()
    db.execute("CREATE TABLE large_values (value FLOAT)")
    db.execute("INSERT INTO large_values VALUES (1e308), (1e308)")
    for function in ("SUM", "AVG"):
        with pytest.raises(QueryError, match="floating-point range"):
            db.execute(f"SELECT {function}(value) FROM large_values")
