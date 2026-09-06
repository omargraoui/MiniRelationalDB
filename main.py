"""Run the demonstration directly from a checkout: python main.py."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from minidb.examples import example_database


def main():
    database = example_database(ROOT / "data" / "examples")
    queries = [
        ("SELECT", "SELECT * FROM departments"),
        ("WHERE + ORDER BY", """SELECT name, salary FROM employees
         WHERE salary > 70000 AND active = TRUE ORDER BY salary DESC"""),
        ("GROUP BY + aggregates", """SELECT department_id, COUNT(*), SUM(salary),
         AVG(salary), MIN(salary), MAX(salary) FROM employees
         GROUP BY department_id ORDER BY department_id"""),
    ]
    for title, sql in queries:
        print(f"\n{title}\n{sql.strip()}")
        result = database.execute(sql)
        print(result)
        print(result.stats)

    sql = """SELECT employees.name, departments.name FROM employees
             INNER JOIN departments ON employees.department_id = departments.id
             ORDER BY employees.name"""
    joined = []
    for strategy in ("nested_loop", "hash"):
        result = database.execute(sql, join_strategy=strategy)
        joined.append(result.rows)
        print(f"\nINNER JOIN ({strategy})\n{result}\n{result.stats}")
    if joined[0] != joined[1]:
        raise AssertionError("Join algorithms returned different results")
    print("Join equivalence: PASS")

    sql = "SELECT name, salary FROM employees WHERE id = 3"
    scan = database.execute(sql)
    database.execute("CREATE INDEX employees_id ON employees (id)")
    indexed = database.execute(sql)
    if scan.rows != indexed.rows or indexed.stats.indexes_used != ["employees.id"]:
        raise AssertionError("Indexed lookup verification failed")
    print(f"\nEquality search\n{indexed}")
    print(f"Full scan: {scan.stats}")
    print(f"Indexed:   {indexed.stats}")
    database.execute("INSERT INTO employees VALUES (9, 'Isabelle Moreau', 10, 88000, 30, TRUE)")
    inserted = database.execute("SELECT name FROM employees WHERE id = 9")
    if inserted.rows != (("Isabelle Moreau",),) or not inserted.stats.indexes_used:
        raise AssertionError("Index maintenance verification failed")
    print("Index lookup and maintenance after INSERT: PASS")


if __name__ == "__main__":
    main()
