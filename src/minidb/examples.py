"""Load repository example CSVs through the typed insertion API."""

import csv
from pathlib import Path

from .database import Database


def example_database(directory: Path) -> Database:
    database = Database()
    database.execute("CREATE TABLE departments (id INT, name TEXT)")
    database.execute("""CREATE TABLE employees (
        id INT, name TEXT, department_id INT, salary FLOAT, age INT, active BOOL
    )""")
    with (directory / "departments.csv").open(encoding="utf-8", newline="") as handle:
        database.get_table("departments").insert_many(
            (int(row["id"]), row["name"]) for row in csv.DictReader(handle)
        )
    with (directory / "employees.csv").open(encoding="utf-8", newline="") as handle:
        database.get_table("employees").insert_many(
            (int(row["id"]), row["name"], int(row["department_id"]), float(row["salary"]),
             int(row["age"]), row["active"].lower() == "true")
            for row in csv.DictReader(handle)
        )
    return database
