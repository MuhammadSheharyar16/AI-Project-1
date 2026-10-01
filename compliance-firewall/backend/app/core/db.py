"""Database engine and session helpers. Any SQLAlchemy URL works (SQLite now, Postgres later)."""

from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine, make_url
from sqlmodel import Session, SQLModel, create_engine


def make_engine(database_url: str) -> Engine:
    url = make_url(database_url)
    connect_args: dict[str, object] = {}
    if url.get_backend_name() == "sqlite":
        connect_args["check_same_thread"] = False
        if url.database and url.database != ":memory:":
            Path(url.database).parent.mkdir(parents=True, exist_ok=True)
    return create_engine(database_url, connect_args=connect_args, pool_pre_ping=True)


def create_tables(engine: Engine) -> None:
    # Import models so their tables are registered on SQLModel.metadata.
    from app.models import audit_entry, audit_review, rule_set  # noqa: F401

    SQLModel.metadata.create_all(engine)


def migrate_missing_columns(engine: Engine) -> list[str]:
    """Additive schema migration: add model columns that an older database lacks.

    `create_all` never alters existing tables, so a database created before a column was added would
    fail at runtime. New columns are added as NULLable (works on SQLite and Postgres); the code reads
    missing values as empty. Columns are never dropped or changed. Returns "table.column" added.
    """
    inspector = inspect(engine)
    added: list[str] = []
    with engine.begin() as conn:
        for table in SQLModel.metadata.sorted_tables:
            if not inspector.has_table(table.name):
                continue
            existing = {c["name"] for c in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing:
                    continue
                col_type = column.type.compile(dialect=engine.dialect)
                conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {col_type}'))
                added.append(f"{table.name}.{column.name}")
    return added


def get_session(engine: Engine) -> Iterator[Session]:
    with Session(engine) as session:
        yield session
