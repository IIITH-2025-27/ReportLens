"""Alembic environment for the lite app. The database URL comes from .env (app.config), never from alembic.ini.

The database is shared with web/backend, so this history is kept in its own version table (alembic_version_v2)
and only the *_v2 tables are compared: autogenerate never proposes dropping the full app's tables.

    alembic upgrade head                              apply all migrations
    alembic revision --autogenerate -m "what"         after changing app/models.py
"""
from alembic import context
from sqlalchemy import engine_from_config, pool

from app import config, models  # noqa: F401  (models: registers the tables)
from app.db import VERSION_TABLE, Base, is_ours

config.require()
target_metadata = Base.metadata
section = context.config.get_section(context.config.config_ini_section, {})
section["sqlalchemy.url"] = config.DATABASE_URL


def include_name(name, type_, parent_names):
    return is_ours(name) if type_ == "table" else True


OPTIONS = dict(target_metadata=target_metadata, compare_type=True, version_table=VERSION_TABLE, include_name=include_name)


def run_migrations_offline() -> None:
    context.configure(url=config.DATABASE_URL, literal_binds=True, **OPTIONS)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, render_as_batch=connection.dialect.name == "sqlite", **OPTIONS)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
