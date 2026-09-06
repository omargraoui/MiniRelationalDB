"""Public errors raised by the tokenizer, parser, and execution engine."""


class MiniDBError(Exception):
    """Base error for expected database failures."""


class SQLSyntaxError(MiniDBError):
    pass


class SchemaError(MiniDBError):
    pass


class TableExistsError(SchemaError):
    pass


class UnknownTableError(SchemaError):
    pass


class UnknownColumnError(SchemaError):
    pass


class AmbiguousColumnError(SchemaError):
    pass


class TypeValidationError(MiniDBError):
    pass


class QueryError(MiniDBError):
    pass


class IndexExistsError(SchemaError):
    pass
