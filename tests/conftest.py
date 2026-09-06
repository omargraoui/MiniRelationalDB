import pytest

from minidb import Database


@pytest.fixture
def db():
    database = Database()
    database.execute("CREATE TABLE employees (id INT, name TEXT, department_id INT, salary FLOAT, active BOOL)")
    database.execute("""INSERT INTO employees VALUES
        (1, 'Alice', 10, 90000, TRUE),
        (2, 'Bob', 20, 60000, FALSE),
        (3, 'Charlie', 10, 80000, TRUE),
        (4, 'Diana', 20, 70000, TRUE),
        (5, 'Emma', 30, 50000, FALSE)""")
    database.execute("CREATE TABLE departments (id INT, name TEXT)")
    database.execute("INSERT INTO departments VALUES (10, 'Engineering'), (20, 'Sales'), (40, 'Research')")
    return database
