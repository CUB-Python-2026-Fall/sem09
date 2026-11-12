"""API tests. Every API test runs twice: once per storage implementation.

Run:  uv run pytest
"""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from askboard import routes
from askboard.main import app
from askboard.storage import InMemoryQuestionStore, SQLiteQuestionStore


@pytest.fixture(params=["memory", "sqlite"])
def client(request, tmp_path, monkeypatch):
    if request.param == "sqlite":
        store = SQLiteQuestionStore(str(tmp_path / "test.db"))
    else:
        store = InMemoryQuestionStore()
    monkeypatch.setattr(routes, "store", store)
    return TestClient(app)


def ask(client, text="What is idempotency?", **extra):
    response = client.post("/questions", json={"text": text, **extra})
    assert response.status_code == 201, response.text
    return response.json()


def ids(response):
    assert response.status_code == 200, response.text
    return [q["id"] for q in response.json()]


def seed(client):
    """Questions 1..4; votes: q1=1, q2=3, q3=0, q4=2; q2 answered."""
    for i in range(1, 5):
        ask(client, f"Question number {i}")
    for qid, n in {1: 1, 2: 3, 4: 2}.items():
        for user in range(n):
            client.put(f"/questions/{qid}/votes/user{user}")
    client.patch("/questions/2", json={"answered": True})


# --- create and read ----------------------------------------------------------------


def test_ask_returns_201_and_the_public_fields(client):
    body = ask(client, author="Ana", author_email="ana@example.com")
    assert body["id"] == 1
    assert body["author"] == "Ana"
    assert body["votes"] == 0
    assert body["answered"] is False
    assert set(body) == {"id", "text", "author", "votes", "answered", "created_at"}


@pytest.mark.parametrize("payload", [{}, {"text": ""}, {"text": "hi"}, {"text": "x" * 281}])
def test_invalid_question_is_422(client, payload):
    assert client.post("/questions", json=payload).status_code == 422


def test_get_one_and_404(client):
    ask(client)
    assert client.get("/questions/1").json()["text"] == "What is idempotency?"
    missing = client.get("/questions/99")
    assert missing.status_code == 404
    assert missing.json() == {"detail": "Question not found"}
    assert client.get("/questions/abc").status_code == 422


# --- votes ----------------------------------------------------------------------------


def test_vote_is_idempotent_per_user(client):
    ask(client)
    for _ in range(5):
        response = client.put("/questions/1/votes/ana")
        assert response.status_code == 200
    assert response.json()["votes"] == 1
    assert client.put("/questions/1/votes/ben").json()["votes"] == 2


def test_vote_on_missing_question_is_404(client):
    assert client.put("/questions/99/votes/ana").status_code == 404


# --- listing --------------------------------------------------------------------------


def test_sort_recent_is_default(client):
    seed(client)
    assert ids(client.get("/questions")) == [4, 3, 2, 1]


def test_sort_by_votes(client):
    seed(client)
    assert ids(client.get("/questions?sort=votes")) == [2, 4, 1, 3]


def test_limit_and_offset(client):
    seed(client)
    assert ids(client.get("/questions?sort=votes&limit=2")) == [2, 4]
    assert ids(client.get("/questions?sort=votes&limit=2&offset=2")) == [1, 3]


def test_filter_answered(client):
    seed(client)
    assert ids(client.get("/questions?answered=false&sort=votes")) == [4, 1, 3]
    assert ids(client.get("/questions?answered=true")) == [2]


@pytest.mark.parametrize(
    "query", ["sort=popular", "limit=0", "limit=101", "offset=-1", "answered=maybe"]
)
def test_bad_query_params_are_422(client, query):
    assert client.get(f"/questions?{query}").status_code == 422


# --- answered and delete -------------------------------------------------------------------


def test_mark_answered_and_404(client):
    ask(client)
    assert client.patch("/questions/1", json={"answered": True}).json()["answered"] is True
    assert client.patch("/questions/9", json={"answered": True}).status_code == 404


def test_delete_is_204_then_404(client):
    ask(client)
    client.put("/questions/1/votes/ana")
    response = client.delete("/questions/1")
    assert response.status_code == 204
    assert response.content == b""
    assert client.get("/questions/1").status_code == 404
    assert client.delete("/questions/1").status_code == 404


# --- storage and restarts ------------------------------------------------------------------------


def test_sqlite_delete_removes_votes(tmp_path):
    store = SQLiteQuestionStore(str(tmp_path / "test.db"))
    question = store.add("Delete me please", "ana", None)
    store.vote(question.id, "ben")
    assert store.delete(question.id)
    with sqlite3.connect(store.db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM votes").fetchone()[0] == 0


def test_sqlite_data_survives_restart(tmp_path):
    db = str(tmp_path / "test.db")
    SQLiteQuestionStore(db).add("Still here after a restart?", "ana", None)
    assert SQLiteQuestionStore(db).get(1).text == "Still here after a restart?"


def test_memory_data_is_lost_on_restart():
    InMemoryQuestionStore().add("Gone after a restart", "ana", None)
    assert InMemoryQuestionStore().list() == []


# --- the demo page --------------------------------------------------------------------------------


def test_board_page_is_served_and_hidden_from_docs(client):
    response = client.get("/board")
    assert response.status_code == 200
    assert "<title>AskBoard</title>" in response.text
    assert "/board" not in client.get("/openapi.json").json()["paths"]
