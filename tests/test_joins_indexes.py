from collections import Counter
import random

import pytest

from minidb import Column, Database
from minidb.errors import AmbiguousColumnError, QueryError, TypeValidationError
from minidb.execution.joins import hash_join, nested_loop_join


@pytest.mark.parametrize("strategy", ["nested_loop", "hash"])
def test_join_correctness_projection_filter_and_group(db, strategy):
    result = db.execute("""SELECT employees.name, departments.name FROM employees
        INNER JOIN departments ON employees.department_id = departments.id
        ORDER BY employees.id""", join_strategy=strategy)
    assert result.rows == (("Alice", "Engineering"), ("Bob", "Sales"), ("Charlie", "Engineering"), ("Diana", "Sales"))
    assert result.stats.rows_scanned == 8
    assert result.stats.join_strategy == strategy
    if strategy == "nested_loop":
        assert result.stats.join_comparisons == 15
    else:
        assert result.stats.hash_build_rows == 3
        assert result.stats.hash_probes == 5
    grouped = db.execute("""SELECT departments.name, COUNT(*), AVG(employees.salary) FROM employees
        INNER JOIN departments ON departments.id = employees.department_id
        WHERE employees.active = TRUE GROUP BY departments.name ORDER BY departments.name""", join_strategy=strategy)
    assert grouped.rows == (("Engineering", 2, 85000.0), ("Sales", 1, 70000.0))
    star = db.execute("SELECT * FROM employees INNER JOIN departments ON employees.department_id = departments.id",
                      join_strategy=strategy)
    assert star.columns[0] == "employees.id" and star.columns[-1] == "departments.name"


def test_duplicate_keys_empty_inputs_and_algorithm_equivalence():
    rng = random.Random(73)
    for n, m in ((0, 0), (0, 5), (5, 0), (1, 1), (30, 20), (60, 40)):
        left = [(i, rng.randrange(6)) for i in range(n)]
        right = [(rng.randrange(8), f"r{i}") for i in range(m)]
        expected = Counter(a + b for a in left for b in right if a[1] == b[0])
        assert Counter(nested_loop_join(iter(left), iter(right), 1, 0)) == expected
        assert Counter(hash_join(iter(left), iter(right), 1, 0)) == expected
    assert list(hash_join([(1,), (1,)], [(1,), (1,)], 0, 0)) == [(1, 1)] * 4


@pytest.mark.parametrize("strategy", ["nested_loop", "hash"])
def test_chained_joins(db, strategy):
    db.execute("CREATE TABLE projects (id INT, department_id INT)")
    db.execute("INSERT INTO projects VALUES (101, 10), (102, 10), (103, 20)")
    result = db.execute("""SELECT employees.id, projects.id FROM employees
        INNER JOIN departments ON employees.department_id = departments.id
        INNER JOIN projects ON projects.department_id = departments.id
        ORDER BY employees.id, projects.id""", join_strategy=strategy)
    assert result.rows == ((1, 101), (1, 102), (2, 103), (3, 101), (3, 102), (4, 103))


def test_join_binding_errors(db):
    with pytest.raises(AmbiguousColumnError):
        db.execute("SELECT id FROM employees INNER JOIN departments ON employees.department_id = departments.id")
    with pytest.raises(QueryError):
        db.execute("SELECT * FROM employees INNER JOIN departments ON employees.id = employees.department_id")
    with pytest.raises(QueryError):
        db.execute("SELECT * FROM employees INNER JOIN employees ON employees.id = employees.id")
    with pytest.raises(TypeValidationError):
        db.execute("SELECT * FROM employees INNER JOIN departments ON employees.name = departments.id")


def test_index_lookup_avoids_full_scan_and_maintains_duplicates(db, monkeypatch):
    table = db.get_table("employees")
    index = table.create_hash_index("department_id")
    assert index.lookup(10) == (0, 2)
    original = table.iter_rows
    accessed_ids = []

    def tracked(row_ids=None):
        assert row_ids is not None, "Indexed lookup unexpectedly requested a full scan"
        accessed_ids.extend(row_ids)
        yield from original(row_ids)

    monkeypatch.setattr(table, "iter_rows", tracked)
    result = db.execute("SELECT name FROM employees WHERE department_id = 10 AND salary > 85000")
    assert result.rows == (("Alice",),)
    assert accessed_ids == [0, 2]
    assert result.stats.rows_scanned == 2
    assert result.stats.indexes_used == ["employees.department_id"]
    table.insert((6, "Frank", 10, 95000, True))
    assert index.lookup(10) == (0, 2, 5)
    assert db.execute("SELECT name FROM employees WHERE department_id = 10 AND salary > 85000").rows == (("Alice",), ("Frank",))
    missing = db.execute("SELECT * FROM employees WHERE department_id = 999")
    assert missing.rows == () and missing.stats.rows_scanned == 0
    assert missing.stats.indexes_used == ["employees.department_id"]


@pytest.mark.parametrize("condition,index_expected", [
    ("id = 3", True), ("3 = employees.id", True), ("id = 3.0", True),
    ("id = 3 AND salary > 0", True), ("id = 3 AND id = 4", True),
    ("id = 3 OR id = 4", False), ("id > 2", False), ("id = department_id", False),
    ("(id = 3 OR id = 4) AND department_id = 10", True),
])
def test_index_and_scan_equivalence_for_safe_predicates(db, condition, index_expected):
    table = db.get_table("employees")
    table.create_hash_index("id")
    table.create_hash_index("department_id")
    sql = f"SELECT name FROM employees WHERE {condition} ORDER BY name"
    indexed = db.execute(sql)
    scanned = db.execute(sql, use_indexes=False)
    assert indexed.rows == scanned.rows
    assert bool(indexed.stats.indexes_used) is index_expected
    assert scanned.stats.indexes_used == []
    assert scanned.stats.rows_scanned == 5


def test_empty_index_and_typed_keys():
    db = Database()
    table = db.create_table("t", [Column("label", "TEXT"), Column("active", "BOOL"), Column("amount", "FLOAT")])
    for column in ("label", "active", "amount"):
        table.create_hash_index(column)
    assert db.execute("SELECT * FROM t WHERE label = 'new'").rows == ()
    table.insert(("new", True, 2))
    for condition in ("label = 'new'", "active = TRUE", "amount = 2"):
        result = db.execute(f"SELECT label FROM t WHERE {condition}")
        assert result.rows == (("new",),) and result.stats.rows_scanned == 1
    with pytest.raises(TypeValidationError):
        db.execute("SELECT * FROM t WHERE active = 1")
