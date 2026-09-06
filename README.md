# MiniRelationalDB

MiniRelationalDB is an in-memory relational database engine built from scratch in
Python 3.13. It **supports a deliberately limited SQL-like subset** and implements
its own tokenizer, recursive descent parser, execution engine, hash indexes, and
two equi-join algorithms. The engine uses only the Python standard library.

This is a Computer Science portfolio project focused on correctness, readable
algorithms, and measurable execution behavior. It does not wrap an existing SQL
engine and does not claim full SQL compatibility.

## Features

- Typed tables with `INT`, `FLOAT`, `TEXT`, and `BOOL` columns.
- SQL table creation, batch insertion, and single-column hash index creation.
- Projection, comparison filters, `AND` / `OR`, and parentheses.
- Sorting by multiple columns or aggregate expressions, with `ASC` / `DESC`.
- Grouping by one or more columns and `COUNT`, `SUM`, `AVG`, `MIN`, `MAX`.
- Explicitly selectable nested-loop and hash inner equi-joins, including chains.
- Equality index access with index maintenance after insertion.
- Structured results, ASCII tables, and measured execution counters.
- Example CSV data, behavior tests, and reproducible small benchmarks.

## Architecture

```text
MiniRelationalDB/
├── src/minidb/
│   ├── __init__.py
│   ├── database.py           # Catalog and public SQL/API entry points
│   ├── table.py              # Append-only row storage and index maintenance
│   ├── schema.py             # Column, DataType, Schema, Value, Row
│   ├── errors.py             # Public database error hierarchy
│   ├── result.py             # QueryResult, ExecutionStats, ASCII formatting
│   ├── examples.py           # Typed CSV example loader
│   ├── parser/
│   │   ├── tokenizer.py      # Lexical analysis with source positions
│   │   ├── ast.py            # Immutable statement/expression nodes
│   │   └── parser.py         # Recursive descent parsing
│   ├── execution/
│   │   ├── binding.py        # Column resolution and type compatibility
│   │   ├── filtering.py      # Predicate evaluation and safe index candidates
│   │   ├── aggregation.py    # Manual groups and aggregates
│   │   ├── joins.py          # Both join implementations
│   │   └── executor.py       # Execution pipeline
│   └── indexes/
│       └── hash_index.py     # value -> row IDs
├── data/examples/            # employees.csv, departments.csv, queries.sql
├── tests/                    # Model, lexer/parser, queries, joins/indexes
├── benchmarks/
│   ├── benchmark.py
│   └── RESULTS.md            # Recorded local run and its methodology
├── main.py
├── pyproject.toml
├── pytest.ini
├── requirements.txt
└── .gitignore
```

Package directories also contain `__init__.py`. Generated CSV measurements are
written to `benchmarks/results.csv` and ignored by Git.

## SQL subset supported

Each `Database.execute()` call accepts **one statement**, with an optional final
semicolon. Keywords and unquoted identifiers are case-insensitive; identifiers
are normalized to lowercase. Identifiers use ASCII letters, digits, and
underscores, beginning with a letter or underscore. Reserved keywords cannot be
used as SQL identifiers. String values are case-sensitive.

```sql
CREATE TABLE employees (
    id INT, name TEXT, department_id INT, salary FLOAT, active BOOL
);

INSERT INTO employees VALUES
    (1, 'Alice', 10, 90000, TRUE),
    (2, 'O''Brien', 20, 75000.5, FALSE);

CREATE INDEX employees_id ON employees (id);

SELECT name, salary
FROM employees
WHERE salary >= 70000 AND (active = TRUE OR department_id = 20)
ORDER BY salary DESC, name ASC;

SELECT department_id, COUNT(*), AVG(salary)
FROM employees
GROUP BY department_id
ORDER BY AVG(salary) DESC;

SELECT employees.name, departments.name
FROM employees
INNER JOIN departments ON employees.department_id = departments.id;
```

| Construct | Supported behavior |
| --- | --- |
| `CREATE TABLE` | Ordered named columns with the four supported types |
| `INSERT INTO ... VALUES` | One or more complete rows; no column list |
| `CREATE INDEX name ON table (column)` | One hash index per column; SQL index names unique in the database |
| `SELECT *` | All columns; `*` must be the only select item and cannot be grouped |
| `SELECT col1, col2` | Qualified or unqualified column references |
| Aggregates | `COUNT(*)`, `COUNT(column)`, `SUM`, `AVG`, `MIN`, `MAX` |
| `WHERE` | `=`, `!=`, `<`, `<=`, `>`, `>=`; column/literal or column/column comparisons |
| Boolean expressions | `AND` binds more tightly than `OR`; parentheses override precedence |
| `GROUP BY` | One or more columns; all selected/ordered nonaggregate columns must be grouped |
| `ORDER BY` | One or more columns/aggregates, including unselected expressions; default `ASC` |
| `INNER JOIN ... ON` | One column equality per join, connecting the new table to a previous table |
| Literals | Signed integers, decimals, scientific notation, single-quoted strings, `TRUE`, `FALSE` |
| Escaping/comments | SQL doubled apostrophes (`'O''Brien'`) and `--` line comments |

Clause order is `SELECT`, `FROM`, joins, `WHERE`, `GROUP BY`, `ORDER BY`.
Aliases, quoted identifiers, arithmetic expressions, and other SQL constructs
outside this subset are rejected. Query results have no promised order without
`ORDER BY`; duplicate rows and duplicate join keys are preserved.

## Relational model

`Database` owns a table catalog. Each `Table` has a name, an immutable `Schema`,
ordered `Column` definitions, and an internal append-only list of rows.
`Row` is an explicit type alias for an immutable tuple of typed Python values;
the schema determines each position's meaning. Row IDs are stable list positions.

| Column type | Accepted Python input | Stored value |
| --- | --- | --- |
| `INT` | `int`, excluding `bool` | Arbitrary-precision Python integer |
| `FLOAT` | Finite `int` or `float`, excluding `bool` | Python float; integer conversion may round |
| `TEXT` | `str` | String |
| `BOOL` | `bool` | Boolean |

Insertion validates arity and types before changing storage. A batch with an
invalid row inserts nothing and leaves indexes unchanged; this is validation
behavior, not a transaction system. There are no `NULL` input values, uniqueness
constraints, primary keys, or foreign keys. Integer/float comparisons are allowed;
other comparisons require the same type, so `TRUE` cannot silently match integer
`1`. Text ordering follows Python's case-sensitive string ordering.

Public `table.rows` returns an immutable snapshot, which costs O(n) to create;
the executor uses `iter_rows()` so indexed access never copies the whole table.
Catalog and index mappings are read-only views.

## Query pipeline

```text
SQL string -> tokenizer -> tokens -> recursive descent parser -> immutable AST
           -> executor: bind names/types -> choose scan or hash-index candidates
           -> joins -> WHERE -> grouping/aggregation -> projection/sorting
           -> QueryResult(columns, rows, stats)
```

### Parser

The tokenizer recognizes keywords, identifiers, numeric/string literals,
operators, punctuation, comments, and end-of-input. Tokens retain source positions
for useful syntax errors. The recursive descent parser constructs dataclass AST
nodes, including statements, column references, comparisons, boolean expressions,
aggregates, and order keys. It rejects trailing tokens and multiple statements.
It has no database/catalog access and calls no SQL parsing library or SQL engine.

### Execution engine

The executor binds every column and checks comparison/aggregate types **before
reading rows**, including when tables or intermediate results are empty. Qualified
names resolve join collisions; ambiguous unqualified names raise an error.

Filters run through the engine's own predicate evaluator. Grouping builds a
dictionary from key tuples to member rows, then manually evaluates each required
aggregate per group. Equal aggregate expressions are reused within each group.
Grouping without aggregates returns one row per group. `SUM` and `AVG` require
numeric columns; `MIN` and `MAX` also support text and booleans.

A global aggregate over empty input returns one row: `COUNT` is `0` and other
aggregates are Python `None`, formatted as `NULL`. Grouped empty input returns zero
rows. This output convention does not add SQL `NULL` literals or three-valued logic.

Sorting uses Python's stable sort, applying keys from right to left for mixed
directions. Projection and sort keys are retained separately, so an unselected
column can be used in `ORDER BY`. Rows and intermediate query results live in
memory; there is no streaming result API or disk spill.

### Nested-loop join

`nested_loop_join()` materializes the right relation, then explicitly compares
each left key with every right key. Each matching pair produces a concatenated
row. The engine counts each key comparison; for a single join this is `n * m`.

```python
result = db.execute(sql, join_strategy="nested_loop")
```

### Hash join

`hash_join()` builds a Python dictionary of key-to-row-list buckets from the
**right** relation, then probes it once for each left row. Lists within buckets
preserve all duplicates, including many-to-many matches. It does not use a table's
persistent hash index. The default join strategy is `"hash"`; the chosen strategy
applies to every join in a statement. There is no smaller-side or cost-based choice.

```python
result = db.execute(sql, join_strategy="hash")
```

### Hash indexing

`HashIndex` maps column values to lists of stable row IDs. Building an index scans
existing rows; later inserts append each new row ID to the appropriate bucket.
Indexes support nonunique values.

```python
db.get_table("employees").create_hash_index("id")
indexed = db.execute("SELECT name FROM employees WHERE id = 42")
scanned = db.execute("SELECT name FROM employees WHERE id = 42", use_indexes=False)
assert indexed.rows == scanned.rows
print(indexed.stats)
```

For a **single-table** query, the executor uses the first available indexed
column/literal equality that is required by the predicate. It supports reversed
equality (`42 = id`) and safe `AND` conjuncts. All residual predicates are still
evaluated on candidates. It never extracts an equality from inside an `OR` branch:
`id = 1 OR id = 2` scans, while `(id = 1 OR id = 2) AND department_id = 10` may use
an index on `department_id`. Range predicates and column/column equalities scan.
No index intersection, index union, or index-based join is implemented.

### Execution statistics

Every query returns its own counters in `result.stats`:

| Counter | What is actually counted |
| --- | --- |
| `rows_scanned` | Base-table rows fetched, including index candidates, summed across tables |
| `indexes_used` | Qualified column names for actual indexed access, or an empty list |
| `join_strategy` | Selected algorithm when a join runs, otherwise `None` |
| `join_comparisons` | Explicit pairwise equality checks in nested-loop joins |
| `hash_build_rows` | Rows inserted into hash-join buckets |
| `hash_probes` | Left rows probing hash-join buckets |

`rows_scanned` does not count repeated comparisons against a materialized right
relation, and it is not a general CPU-work counter. Hash joins leave
`join_comparisons` at zero because dictionary-internal collision comparisons are
not instrumented. For chained joins, join-work counters sum across stages.

## Complexity

Let `n` and `m` be input row counts, `k` matching index candidates, `r` output
rows, `g` groups, `a` distinct aggregate expressions, and `s` sort keys. Bounds
below assume fixed row width, bounded-size keys, and normal hash behavior.

| Operation | Time | Additional storage / nuance |
| --- | --- | --- |
| Tokenize/parse | O(L) for input length L in ordinary inputs | O(L) tokens/AST; nested conditions use recursion |
| Full equality scan | O(n) | Plus O(r) materialized results |
| Hash index construction | O(n) average | O(n) row IDs and buckets |
| Hash index lookup | O(1) average bucket access + O(k) candidate handling | Lookup copies k row IDs; residual filtering/projection still costs work |
| Insert with h indexes | O(h) average index maintenance per row | Plus schema validation and amortized row append |
| Nested-loop join | O(n * m + r) | O(m) right-side buffer, plus materialized output |
| Hash join | O(n + m + r) average | O(m) right-side buckets, plus materialized output |
| Grouping and aggregation | O(n * (1 + a)) average | O(n + g) group membership storage, plus group outputs |
| ORDER BY | O(s * r log r) upper bound | Stable sorting and retained output/sort keys |

Hash operations are not worst-case constant time: collisions and pathological key
distributions can degrade them. A many-to-many join can emit O(n * m) rows even
with a hash join, so output cost cannot be omitted. Long strings, large integers,
wide rows, and many predicates add comparison, hashing, validation, or copying
cost. Binding and query parsing also add overhead to short queries.

## Installation

Use Python **3.13 or newer**. From the repository root, on PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

On macOS/Linux, activate with `source .venv/bin/activate` instead. If PowerShell
activation is unavailable, use `.\.venv\Scripts\python.exe` directly in place of
`python` in the following commands.

The engine has **zero runtime dependencies**. `pytest` is the only direct test
dependency; its own dependencies are installed by pip. The demo, benchmarks, and
pytest configuration load the local `src` tree directly. To import `minidb` from
other scripts or a Python shell, optionally install the package:

```console
python -m pip install -e .
```

Editable packaging uses setuptools as a build dependency, not a query dependency.

## Usage and examples

```console
python main.py
```

The demo loads `data/examples/employees.csv` and `departments.csv`, displays
selection, filtering, sorting, and all five aggregates, then runs both joins. It
checks their equality and verifies indexed lookup before and after insertion.
Additional example statements are in `data/examples/queries.sql`; execute them
individually rather than passing the whole file to `execute()`.

After an editable installation, the Python API is:

```python
from minidb import Column, Database
from minidb.errors import MiniDBError

db = Database()
employees = db.create_table("employees", [
    Column("id", "INT"), Column("name", "TEXT"), Column("salary", "FLOAT")
])
employees.insert((1, "Alice", 90000))
db.execute("INSERT INTO employees VALUES (2, 'Bob', 60000)")

result = db.execute("SELECT name, salary FROM employees WHERE salary > 70000")
assert result.columns == ("name", "salary")
assert result.rows == (("Alice", 90000.0),)
print(result)
print(result.stats)

try:
    db.execute("SELECT missing FROM employees")
except MiniDBError as exc:
    print(exc)
```

DDL results provide `message`; insert results also provide `affected_rows`.
Expected errors have dedicated subclasses for syntax, duplicate/unknown tables,
unknown/ambiguous columns, invalid types, duplicate indexes, and invalid queries.

## Testing

```console
python -m pytest -q
python main.py
python benchmarks/benchmark.py
python -m pip check
```

Tests cover typed insertion and failed-batch atomic validation; tokenizer tokens,
escaping and AST structure; predicates and precedence; projection and sorting;
all aggregates and empty input; name/type validation; both join algorithms,
duplicate keys and chained joins; index creation, maintenance, actual candidate
reads, scan equivalence, and unsafe `OR` cases. Deterministic generated joins are
checked against an explicit reference result, preserving duplicate multiplicity.
No test uses another SQL engine as an oracle.

When Git is initialized, also run `git diff --check`. Repository creation,
commits, and pushes are not performed by project scripts.

## Benchmark methodology

```console
python benchmarks/benchmark.py --repeats 7 --output benchmarks/results.csv
```

- Search tables contain 1,000, 10,000, and 50,000 unique IDs. The same equality
  query selects an existing middle ID with forced scan and with indexed access.
- Join sizes are 100 x 50, 500 x 250, and 1,000 x 500. Right-side keys occur twice,
  exercising duplicate handling and yielding twice the left input row count.
- Each algorithm gets one untimed warm-up and seven timed repetitions by default.
  `time.perf_counter()` measures each complete `Database.execute()` call, including
  parsing, binding, execution counters, projection, and result materialization.
- CSV values report the median, input/output row counts, actual access counters,
  Python/platform versions, and a separate one-shot index-construction time.
  Data generation, table insertion, persistent index building, result comparison,
  printing, and CSV writing are excluded from query timing. Each hash-join timing
  includes rebuilding its temporary hash table.
- The script checks identical results for both searches, multiset equality for
  both joins, expected result sizes, and actual scan/index access paths.

These are small local benchmarks, not throughput or production performance
claims. Short timings are noisy, order/cache effects remain, and results depend
on hardware, Python, and system activity. The script does not benchmark memory or
worst-case hash collisions. See [the recorded run](benchmarks/RESULTS.md) for actual
measurements rather than universal speedup claims.

## Limitations

- All storage is in memory and lost when the process exits; CSVs are examples,
  not persistent database storage.
- No updates, deletes, table/index dropping, schema alteration, or constraints.
- No SQL `NULL` inputs, aliases, self-joins, outer/cross joins, `DISTINCT`, `HAVING`,
  `LIMIT`, `LIKE`, `IN`, `NOT`, expressions, subqueries, or complete SQL grammar.
- No transactions, ACID guarantees, concurrent access, WAL, crash recovery,
  permissions, authentication, network server, frontend, web API, or distribution.
- No B-tree, range index, advanced optimizer, predicate pushdown across joins,
  persistent-index joins, disk spill, or streaming results.
- Float arithmetic uses ordinary binary floats; rounding is expected. Nonfinite
  input and overflowing aggregate sums are rejected. `AVG` also rejects an
  integer result that cannot be represented as a float; an overflowing float
  intermediate sum is rejected even if its mathematical average would be finite.
- Deeply nested expressions are subject to Python's recursion limit. There is no
  untrusted-input resource budget or production hardening.

The implemented and tested scope supports this portfolio statement:

> Built a relational database engine from scratch with SQL-style query parsing,
> filtering, grouping, hash indexing, and nested-loop and hash-join execution.
