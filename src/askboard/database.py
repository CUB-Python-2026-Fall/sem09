"""SQLite connection and schema (standard library sqlite3)."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

SCHEMA = """
CREATE TABLE IF NOT EXISTS questions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    text         TEXT    NOT NULL,
    author       TEXT    NOT NULL,
    author_email TEXT,
    answered     INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS votes (
    question_id INTEGER NOT NULL REFERENCES questions (id) ON DELETE CASCADE,
    voter       TEXT    NOT NULL,
    UNIQUE (question_id, voter)
);
"""


@contextmanager
def connect(db_path: str) -> Iterator[sqlite3.Connection]:
    """Open a connection: one transaction that commits on success, rolls back
    on error, and always closes the connection."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row  # rows can be read by column name
    conn.execute("PRAGMA foreign_keys = ON")  # off by default in SQLite, per connection
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def create_tables(db_path: str) -> None:
    with connect(db_path) as conn:
        conn.executescript(SCHEMA)
