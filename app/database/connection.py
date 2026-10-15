import os
import sqlite3
from typing import Any, Dict, List, Tuple
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from app.config import settings


def get_absolute_db_path(db_path: str = None) -> str:
    path = db_path or settings.DB_PATH
    return os.path.abspath(path)


def get_readwrite_engine(db_path: str = None) -> Engine:
    """Returns a SQLAlchemy engine with read-write access for database initialization."""
    abs_path = get_absolute_db_path(db_path)
    return create_engine(f"sqlite:///{abs_path}", echo=False)


def get_readonly_connection(db_path: str = None) -> sqlite3.Connection:
    """
    Returns a native SQLite connection opened in strict READ-ONLY URI mode.
    Any attempt to modify the database raises sqlite3.OperationalError.
    """
    abs_path = get_absolute_db_path(db_path)
    # Ensure URI format is compatible across Windows and Unix
    uri = f"file:{abs_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def execute_readonly_query(
    sql: str, db_path: str = None
) -> Tuple[List[str], List[Dict[str, Any]]]:
    """
    Executes a SELECT query on a Read-Only SQLite connection.
    Returns (column_names, rows_as_dicts).
    """
    conn = get_readonly_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(sql)
        description = cursor.description
        if not description:
            return [], []

        columns = [col[0] for col in description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        return columns, rows
    finally:
        conn.close()


def get_database_schema_ddl(db_path: str = None) -> str:
    """
    Retrieves the exact CREATE TABLE DDLs from sqlite_master for all user tables.
    Used for Schema Pruning and Prompt Engineering.
    """
    abs_path = get_absolute_db_path(db_path)
    if not os.path.exists(abs_path):
        return ""

    conn = get_readonly_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT name, sql FROM sqlite_master
            WHERE type='table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name;
            """
        )
        ddls = []
        for name, sql in cursor.fetchall():
            if sql:
                ddls.append(f"-- Table: {name}\n{sql.strip()};")
        return "\n\n".join(ddls)
    finally:
        conn.close()
