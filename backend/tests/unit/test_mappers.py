"""Unit test — all ORM relationships must resolve without a database.

Catches AmbiguousForeignKeysError-style mistakes (e.g. a relationship to a
table that also carries owner/modified_by FKs to users) at test time instead
of first query time.
"""

from sqlalchemy.orm import configure_mappers


def test_all_mappers_configure():
    from app.models import accounts, core  # noqa: F401 — register every model

    configure_mappers()
