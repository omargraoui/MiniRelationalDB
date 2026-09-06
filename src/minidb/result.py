from dataclasses import dataclass, field

from .schema import Value


@dataclass
class ExecutionStats:
    # Base rows fetched, including index candidates. Join work is counted separately.
    rows_scanned: int = 0
    indexes_used: list[str] = field(default_factory=list)
    join_strategy: str | None = None
    join_comparisons: int = 0
    hash_build_rows: int = 0
    hash_probes: int = 0

    def __str__(self) -> str:
        return (
            f"Rows scanned: {self.rows_scanned}; "
            f"Index used: {', '.join(self.indexes_used) or 'none'}; "
            f"Join strategy: {self.join_strategy or 'none'}; "
            f"Join comparisons: {self.join_comparisons}; "
            f"Hash build rows: {self.hash_build_rows}; Hash probes: {self.hash_probes}"
        )


@dataclass(frozen=True)
class QueryResult:
    columns: tuple[str, ...] = ()
    rows: tuple[tuple[Value | None, ...], ...] = ()
    stats: ExecutionStats = field(default_factory=ExecutionStats)
    affected_rows: int = 0
    message: str = ""

    def __str__(self) -> str:
        if not self.columns:
            return self.message
        cells = [tuple("NULL" if value is None else str(value) for value in row) for row in self.rows]
        widths = [max(len(name), *(len(row[i]) for row in cells)) if cells else len(name)
                  for i, name in enumerate(self.columns)]
        border = "+" + "+".join("-" * (width + 2) for width in widths) + "+"

        def line(values):
            return "| " + " | ".join(value.ljust(width) for value, width in zip(values, widths)) + " |"

        return "\n".join([border, line(self.columns), border, *(line(row) for row in cells), border,
                          f"({len(self.rows)} rows)"])
