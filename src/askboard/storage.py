"""Storage: where questions and votes are kept.

QuestionStore is the contract (a Protocol) that the routes depend on.
Two implementations follow it:

- InMemoryQuestionStore: plain Python dicts; everything is lost on restart.
- SQLiteQuestionStore: a SQLite file; all the SQL of the app lives here.

The routes never know which one they are using.
"""

import sqlite3
import threading
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Literal, Protocol

from askboard import config
from askboard.database import connect, create_tables

SortOrder = Literal["recent", "votes"]


@dataclass
class Question:
    """A question as the app stores it (including private fields)."""

    id: int
    text: str
    author: str
    author_email: str | None
    answered: bool
    created_at: datetime
    votes: int = 0


class QuestionStore(Protocol):
    """What any storage for AskBoard must be able to do."""

    def add(self, text: str, author: str, author_email: str | None) -> Question: ...

    def get(self, question_id: int) -> Question | None: ...

    def list(
        self,
        sort: SortOrder = "recent",
        limit: int = 20,
        offset: int = 0,
        answered: bool | None = None,
    ) -> list[Question]: ...

    def vote(self, question_id: int, voter: str) -> Question | None:
        """One vote per voter; voting again changes nothing. None if not found."""
        ...

    def set_answered(self, question_id: int, answered: bool) -> Question | None: ...

    def delete(self, question_id: int) -> bool:
        """Delete a question and its votes. False if it did not exist."""
        ...


# --- In memory ------------------------------------------------------------------


class InMemoryQuestionStore:
    def __init__(self) -> None:
        self._questions: dict[int, Question] = {}
        self._voters: dict[int, set[str]] = {}
        self._next_id = 1
        self._lock = threading.Lock()  # requests run in parallel threads

    def _public(self, question: Question) -> Question:
        """A copy with the current vote count, so callers can't change our data."""
        return replace(question, votes=len(self._voters[question.id]))

    def add(self, text: str, author: str, author_email: str | None) -> Question:
        with self._lock:
            question = Question(
                id=self._next_id,
                text=text,
                author=author,
                author_email=author_email,
                answered=False,
                created_at=datetime.now(timezone.utc),
            )
            self._questions[question.id] = question
            self._voters[question.id] = set()
            self._next_id += 1
            return self._public(question)

    def get(self, question_id: int) -> Question | None:
        with self._lock:
            question = self._questions.get(question_id)
            return self._public(question) if question else None

    def list(
        self,
        sort: SortOrder = "recent",
        limit: int = 20,
        offset: int = 0,
        answered: bool | None = None,
    ) -> list[Question]:
        with self._lock:
            items = [self._public(q) for q in self._questions.values()]
        if answered is not None:
            items = [q for q in items if q.answered == answered]
        if sort == "votes":
            items.sort(key=lambda q: (q.votes, q.id), reverse=True)
        else:  # "recent": newest first
            items.sort(key=lambda q: q.id, reverse=True)
        return items[offset : offset + limit]

    def vote(self, question_id: int, voter: str) -> Question | None:
        with self._lock:
            question = self._questions.get(question_id)
            if question is None:
                return None
            self._voters[question_id].add(voter)  # a set: the same voter counts once
            return self._public(question)

    def set_answered(self, question_id: int, answered: bool) -> Question | None:
        with self._lock:
            question = self._questions.get(question_id)
            if question is None:
                return None
            question.answered = answered
            return self._public(question)

    def delete(self, question_id: int) -> bool:
        with self._lock:
            if self._questions.pop(question_id, None) is None:
                return False
            del self._voters[question_id]
            return True


# --- SQLite ---------------------------------------------------------------------


class SQLiteQuestionStore:
    # Every read goes through this query, so `votes` is always the number of
    # rows in the votes table for that question.
    SELECT = """
        SELECT q.id, q.text, q.author, q.author_email, q.answered, q.created_at,
               COUNT(v.voter) AS votes
        FROM questions AS q
        LEFT JOIN votes AS v ON v.question_id = q.id
    """

    # ORDER BY cannot take a "?" parameter, so only these fixed strings ever
    # go into the SQL (never text that came from a request).
    ORDER_BY = {"recent": "q.id DESC", "votes": "votes DESC, q.id DESC"}

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        create_tables(db_path)

    @staticmethod
    def _to_question(row: sqlite3.Row) -> Question:
        return Question(
            id=row["id"],
            text=row["text"],
            author=row["author"],
            author_email=row["author_email"],
            answered=bool(row["answered"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            votes=row["votes"],
        )

    def add(self, text: str, author: str, author_email: str | None) -> Question:
        with connect(self.db_path) as conn:
            cursor = conn.execute(
                "INSERT INTO questions (text, author, author_email, created_at)"
                " VALUES (?, ?, ?, ?)",
                (text, author, author_email, datetime.now(timezone.utc).isoformat()),
            )
        return self.get(cursor.lastrowid)

    def get(self, question_id: int) -> Question | None:
        with connect(self.db_path) as conn:
            row = conn.execute(
                self.SELECT + " WHERE q.id = ? GROUP BY q.id", (question_id,)
            ).fetchone()
        return self._to_question(row) if row else None

    def list(
        self,
        sort: SortOrder = "recent",
        limit: int = 20,
        offset: int = 0,
        answered: bool | None = None,
    ) -> list[Question]:
        where, params = "", []
        if answered is not None:
            where = "WHERE q.answered = ?"
            params.append(answered)
        sql = (
            self.SELECT
            + f" {where} GROUP BY q.id ORDER BY {self.ORDER_BY[sort]} LIMIT ? OFFSET ?"
        )
        with connect(self.db_path) as conn:
            rows = conn.execute(sql, (*params, limit, offset)).fetchall()
        return [self._to_question(row) for row in rows]

    def vote(self, question_id: int, voter: str) -> Question | None:
        with connect(self.db_path) as conn:
            exists = conn.execute(
                "SELECT 1 FROM questions WHERE id = ?", (question_id,)
            ).fetchone()
            if exists is None:
                return None
            # A second vote from the same voter hits UNIQUE (question_id, voter)
            # and is ignored, so voting again changes nothing.
            conn.execute(
                "INSERT OR IGNORE INTO votes (question_id, voter) VALUES (?, ?)",
                (question_id, voter),
            )
        return self.get(question_id)

    def set_answered(self, question_id: int, answered: bool) -> Question | None:
        with connect(self.db_path) as conn:
            conn.execute(
                "UPDATE questions SET answered = ? WHERE id = ?", (answered, question_id)
            )
        return self.get(question_id)

    def delete(self, question_id: int) -> bool:
        # The question's votes are deleted by the database: ON DELETE CASCADE.
        with connect(self.db_path) as conn:
            cursor = conn.execute("DELETE FROM questions WHERE id = ?", (question_id,))
        return cursor.rowcount == 1


def make_store() -> QuestionStore:
    """The store chosen in config: in memory (default) or SQLite."""
    if config.STORAGE == "sqlite":
        return SQLiteQuestionStore(config.DB_PATH)
    return InMemoryQuestionStore()
