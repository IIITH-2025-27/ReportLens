from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from . import config

config.require()
_args = {"check_same_thread": False} if config.DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(config.DATABASE_URL, pool_pre_ping=True, connect_args=_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

# The lite app shares the database with web/backend. Its tables all end in this suffix and its Alembic history
# lives in its own version table, so neither app's migrations touch the other's tables.
SUFFIX = "_v2"
VERSION_TABLE = "alembic_version" + SUFFIX


def is_ours(table_name: str) -> bool:
    return table_name.endswith(SUFFIX)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
