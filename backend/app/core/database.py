from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(settings.DATABASE_URL, connect_args=connect_args)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    # Import all models so that Base.metadata knows about them
    from app.models import api_key, job, user  # noqa: F401
    Base.metadata.create_all(bind=engine)
    _apply_migrations()


def _apply_migrations() -> None:
    """Lightweight schema migrations for columns added after initial deployment.

    SQLAlchemy's create_all() only creates *missing tables*, it never alters
    existing ones.  This function inspects the live schema and issues ALTER
    TABLE statements for any new columns so that existing SQLite databases are
    upgraded automatically on startup without requiring Alembic.
    """
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    tables = inspector.get_table_names()

    _add_column_if_missing(inspector, text, tables, "jobs", "task_id", "TEXT")


def _add_column_if_missing(inspector, text, tables, table: str, column: str, col_type: str) -> None:
    if table not in tables:
        return
    existing = {c["name"] for c in inspector.get_columns(table)}
    if column not in existing:
        with engine.connect() as conn:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))
            conn.commit()
