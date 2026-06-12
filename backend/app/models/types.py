"""Custom PostgreSQL column types."""

from typing import Any

from sqlalchemy import types


class Ltree(types.UserDefinedType):
    """PostgreSQL ``ltree`` materialised-path type (used for account trees).

    Values are plain dot-separated strings on the Python side, e.g.
    ``"assets.current_assets.cash"``.
    """

    cache_ok = True

    def get_col_spec(self, **kw: Any) -> str:
        return "ltree"

    def bind_processor(self, dialect: Any):
        def process(value: str | None) -> str | None:
            return value

        return process

    def result_processor(self, dialect: Any, coltype: Any):
        def process(value: Any) -> str | None:
            return None if value is None else str(value)

        return process
