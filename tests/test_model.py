import pytest

from minidb import Column, Database, DataType, Schema
from minidb.errors import (
    IndexExistsError, SchemaError, TableExistsError, TypeValidationError,
    UnknownColumnError, UnknownTableError,
)


def test_create_and_insert_through_both_apis():
    db = Database()
    table = db.create_table("Things", Schema((Column("id", "int"), Column("price", DataType.FLOAT))))
    assert table.name == "things"
    assert table.insert((1, 4)) == 0
    result = db.execute("INSERT INTO things VALUES (2, -1.5), (3, +2e2)")
    assert result.affected_rows == 2
    assert table.rows == ((1, 4.0), (2, -1.5), (3, 200.0))
    assert type(table.rows[0][1]) is float
    assert db.get_table("THINGS") is table


@pytest.mark.parametrize("data_type,value", [
    ("INT", True), ("INT", 1.5), ("INT", "1"), ("FLOAT", False),
    ("FLOAT", float("nan")), ("FLOAT", float("inf")), ("FLOAT", 10**400),
    ("TEXT", 1), ("BOOL", 1), ("BOOL", "true"), ("TEXT", None),
])
def test_invalid_types_leave_table_unchanged(data_type, value):
    table = Database().create_table("t", [Column("v", data_type)])
    with pytest.raises(TypeValidationError):
        table.insert((value,))
    assert len(table) == 0


def test_schema_errors_and_unknown_objects(db):
    with pytest.raises(TableExistsError):
        db.execute("CREATE TABLE employees (id INT)")
    with pytest.raises(UnknownTableError):
        db.execute("INSERT INTO missing VALUES (1)")
    with pytest.raises(SchemaError):
        db.execute("CREATE TABLE bad (id INT, ID TEXT)")
    with pytest.raises(SchemaError):
        Schema(())
    with pytest.raises(SchemaError):
        Column("bad-name", "INT")
    with pytest.raises(SchemaError):
        Column("id", "DATE")
    with pytest.raises(UnknownColumnError):
        db.get_table("employees").create_hash_index("missing")


def test_wrong_arity_and_atomic_batch_validation(db):
    table = db.get_table("employees")
    index = table.create_hash_index("id")
    before = table.rows
    with pytest.raises(TypeValidationError):
        db.execute("INSERT INTO employees VALUES (6, 'Frank')")
    with pytest.raises(TypeValidationError):
        db.execute("""INSERT INTO employees VALUES
            (6, 'Frank', 10, 80000, TRUE), (7, 'Grace', 10, 'bad', TRUE)""")
    assert table.rows == before
    assert index.lookup(6) == ()


def test_index_names_and_duplicate_columns(db):
    db.execute("CREATE INDEX employee_id ON employees (id)")
    with pytest.raises(IndexExistsError):
        db.execute("CREATE INDEX employee_id ON departments (id)")
    with pytest.raises(IndexExistsError):
        db.get_table("employees").create_hash_index("id")


def test_public_rows_and_catalog_cannot_be_mutated(db):
    table = db.get_table("employees")
    with pytest.raises(TypeError):
        table.rows[0][0] = 99
    with pytest.raises(TypeError):
        db.tables["other"] = table
    with pytest.raises(TypeError):
        table.indexes["id"] = None
