"""Alembic environment. The database URL comes from .env (app.config), never from alembic.ini.

    alembic upgrade head                              apply all migrations
    alembic revision --autogenerate -m "what"         after changing app/models.py
"""
from alembic import context
from sqlalchemy import engine_from_config, pool

from app import config, models  # noqa: F401  (models: registers the tables)
from app.db import Base

config.require()
target_metadata = Base.metadata
section = context.config.get_section(context.config.config_ini_section, {})
section["sqlalchemy.url"] = config.DATABASE_URL


def run_migrations_offline() -> None:
    context.configure(url=config.DATABASE_URL, target_metadata=target_metadata, literal_binds=True, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True,
                          render_as_batch=connection.dialect.name == "sqlite")
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
