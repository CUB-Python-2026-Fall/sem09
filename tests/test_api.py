"""API tests. Every API test runs twice: once per storage implementation.

Run:  uv run pytest
"""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from askboard import auth, config, routes
from askboard.main import app
from askboard.rate_limit import writes
from askboard.storage import InMemoryQuestionStore, SQLiteQuestionStore


@pytest.fixture(params=["memory", "sqlite"])
def store(request, tmp_path, monkeypatch):
    if request.param == "sqlite":
        store = SQLiteQuestionStore(str(tmp_path / "test.db"))
    else:
        store = InMemoryQuestionStore()
    monkeypatch.setattr(routes, "store", store)
    return store


@pytest.fixture
def client(store):
    auth.sessions.clear()
    writes.reset()
    return TestClient(app)


def login(client, name="ana", password=None):
    body = {"name": name} | ({"password": password} if password else {})
    response = client.post("/login", json=body)
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def ana(client):
    return login(client, "ana")


@pytest.fixture
def speaker(client):
    return login(client, "eva", config.SPEAKER_PASSWORD)


def ask(client, headers, text="What is idempotency?", **extra):
    response = client.post("/questions", json={"text": text, **extra}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def ids(response):
    assert response.status_code == 200, response.text
    return [q["id"] for q in response.json()]


def seed(client, speaker):
    """Questions 1..4; votes: q1=1, q2=3, q3=0, q4=2; q2 answered."""
    for i in range(1, 5):
        ask(client, speaker, f"Question number {i}")
    for qid, n in {1: 1, 2: 3, 4: 2}.items():
        for user in range(n):
            client.put(f"/questions/{qid}/vote", headers=login(client, f"user{user}"))
    client.patch("/questions/2", json={"answered": True}, headers=speaker)


# --- authentication (2 tests) ------------------------------------------------------


def test_writes_need_login_401(client):
    response = client.post("/questions", json={"text": "Who am I?"})
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    bad_token = {"Authorization": "Bearer made-up"}
    assert client.put("/questions/1/vote", headers=bad_token).status_code == 401
    assert client.post("/login", json={"name": "eva", "password": "nope"}).status_code == 401


def test_only_the_speaker_can_moderate_403(client, ana, speaker):
    question = ask(client, ana)
    assert question["author"] == "ana"  # the author comes from the token
    assert client.patch("/questions/1", json={"answered": True}, headers=ana).status_code == 403
    assert client.delete("/questions/1", headers=ana).status_code == 403
    assert client.delete("/questions/1", headers=speaker).status_code == 204


# --- create and read ----------------------------------------------------------------


def test_ask_returns_201(client, ana):
    body = ask(client, ana)
    assert body["id"] == 1
    assert body["votes"] == 0
    assert body["answered"] is False


@pytest.mark.parametrize("payload", [{}, {"text": ""}, {"text": "hi"}, {"text": "x" * 281}])
def test_invalid_question_is_422(client, ana, payload):
    assert client.post("/questions", json=payload, headers=ana).status_code == 422


def test_get_one_and_404(client, ana):
    ask(client, ana)
    assert client.get("/questions/1").json()["text"] == "What is idempotency?"
    missing = client.get("/questions/99")
    assert missing.status_code == 404
    assert missing.json() == {"detail": "Question not found"}
    assert client.get("/questions/abc").status_code == 422


# --- votes ----------------------------------------------------------------------------


def test_vote_is_idempotent_per_user(client, ana):
    ask(client, ana)
    for _ in range(5):
        response = client.put("/questions/1/vote", headers=ana)
        assert response.status_code == 200
    assert response.json()["votes"] == 1
    assert client.put("/questions/1/vote", headers=login(client, "ben")).json()["votes"] == 2


def test_vote_on_missing_question_is_404(client, ana):
    assert client.put("/questions/99/vote", headers=ana).status_code == 404


# --- listing --------------------------------------------------------------------------


def test_sort_recent_is_default(client, speaker):
    seed(client, speaker)
    assert ids(client.get("/questions")) == [4, 3, 2, 1]


def test_sort_by_votes(client, speaker):
    seed(client, speaker)
    assert ids(client.get("/questions?sort=votes")) == [2, 4, 1, 3]


def test_limit_and_offset(client, speaker):
    seed(client, speaker)
    assert ids(client.get("/questions?sort=votes&limit=2")) == [2, 4]
    assert ids(client.get("/questions?sort=votes&limit=2&offset=2")) == [1, 3]


def test_filter_answered(client, speaker):
    seed(client, speaker)
    assert ids(client.get("/questions?answered=false&sort=votes")) == [4, 1, 3]
    assert ids(client.get("/questions?answered=true")) == [2]


@pytest.mark.parametrize(
    "query", ["sort=popular", "limit=0", "limit=101", "offset=-1", "answered=maybe"]
)
def test_bad_query_params_are_422(client, query):
    assert client.get(f"/questions?{query}").status_code == 422


# --- speaker: answered and delete -------------------------------------------------------


def test_mark_answered_and_404(client, ana, speaker):
    ask(client, ana)
    response = client.patch("/questions/1", json={"answered": True}, headers=speaker)
    assert response.json()["answered"] is True
    assert client.patch("/questions/9", json={"answered": True}, headers=speaker).status_code == 404


def test_delete_is_204_then_404(client, ana, speaker):
    ask(client, ana)
    client.put("/questions/1/vote", headers=ana)
    response = client.delete("/questions/1", headers=speaker)
    assert response.status_code == 204
    assert response.content == b""
    assert client.get("/questions/1").status_code == 404
    assert client.delete("/questions/1", headers=speaker).status_code == 404


# --- rate limiting (2 tests) ---------------------------------------------------------


def test_over_the_limit_is_429_with_retry_after(client, ana):
    for i in range(config.RATE_LIMIT):
        ask(client, ana, f"Question number {i}")
    response = client.put("/questions/1/vote", headers=ana)  # votes count too
    assert response.status_code == 429
    assert 1 <= int(response.headers["Retry-After"]) <= config.RATE_WINDOW
    assert client.get("/questions").status_code == 200  # reading is never limited


def test_limit_is_per_user(client, ana):
    for i in range(config.RATE_LIMIT):
        ask(client, ana, f"Question number {i}")
    assert client.put("/questions/1/vote", headers=ana).status_code == 429
    assert client.put("/questions/1/vote", headers=login(client, "ben")).status_code == 200


# --- caching (2 tests) ------------------------------------------------------------------


def test_unchanged_data_is_304(client, ana):
    ask(client, ana)
    first = client.get("/questions")
    etag = first.headers["ETag"]
    again = client.get("/questions", headers={"If-None-Match": etag})
    assert again.status_code == 304
    assert again.content == b""
    assert again.headers["ETag"] == etag


def test_changed_data_gets_a_new_etag(client, ana):
    ask(client, ana)
    etag = client.get("/questions/1").headers["ETag"]
    client.put("/questions/1/vote", headers=ana)
    changed = client.get("/questions/1", headers={"If-None-Match": etag})
    assert changed.status_code == 200
    assert changed.headers["ETag"] != etag
    assert changed.json()["votes"] == 1


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
