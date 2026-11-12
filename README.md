# AskBoard

A live Q&A board API: people log in, post questions and upvote them, and the speaker marks them as answered. Built with FastAPI. Data is kept in memory by default, or in SQLite (the standard library `sqlite3` module, no ORM).

Besides the usual create / read / list with validation, it has the three things almost every real API needs: **authentication** (bearer tokens, 401 vs 403), **rate limiting** (429 with `Retry-After`) and **HTTP caching** (`ETag` and 304 Not Modified).

## Run it

You need [uv](https://docs.astral.sh/uv/). From this folder:

```bash
uv sync                                      # creates .venv with the app, Jupyter and pytest
uv run uvicorn askboard.main:app --reload
```

Then open:

- http://127.0.0.1:8000/board for the board (questions sorted by votes, refreshes every 2 seconds)
- http://127.0.0.1:8000/docs for the interactive API docs

By default the data is kept in memory and is lost when the server stops. To keep it in a SQLite file (`askboard.db`, or the path in `ASKBOARD_DB`):

```bash
ASKBOARD_STORAGE=sqlite uv run uvicorn askboard.main:app --reload
```

## Tests

```bash
uv run pytest
```

## Build a package

```bash
uv build        # writes dist/askboard-0.1.0.tar.gz and a .whl
```

## Notebook

```bash
uv run jupyter notebook
```

The notebook uses the same `.venv` as the app (in PyCharm or VS Code, select `sem09/.venv` as the interpreter / kernel).

## Structure

```
pyproject.toml, uv.lock   the uv project (dependencies for the app, Jupyter and tests)
src/askboard/
  main.py        creates the app: adds the routers and the /board page
  routes.py      HTTP layer for /questions: URLs, methods, status codes, who may do what
  auth.py        POST /login, bearer tokens, the current_user / speaker dependencies
  rate_limit.py  RateLimiter (sliding window per user), 429 + Retry-After
  cache.py       ETag / If-None-Match / 304 for GET responses
  models.py      Pydantic API models: LoginIn, TokenOut, QuestionIn, QuestionUpdate, QuestionOut
  storage.py     QuestionStore (a Protocol), the Question record, and two stores:
                 InMemoryQuestionStore and SQLiteQuestionStore (all the SQL lives here);
                 make_store() picks one from config
  database.py    SQLite connection (one transaction per call) and the schema
  config.py      settings from environment variables
  static/board.html   the demo page; it only calls the API
tests/
  test_api.py
```

## API

| Method | URL | Who | What it does | Success |
|---|---|---|---|---|
| `POST` | `/login` | anyone | `{"name": "ana"}` gives an audience token; adding `"password"` (the speaker password) gives a speaker token | `200` |
| `POST` | `/questions` | logged in, rate limited | Ask a question (`text`, optional `author_email`); the author is the logged-in user | `201` |
| `GET` | `/questions?sort=votes&limit=20&offset=0&answered=false` | anyone | List questions. `sort` is `recent` (default) or `votes`. Sends an `ETag` | `200` / `304` |
| `GET` | `/questions/{id}` | anyone | One question. Sends an `ETag` | `200` / `304` |
| `PUT` | `/questions/{id}/vote` | logged in, rate limited | Vote as the logged-in user. Repeating it changes nothing | `200` |
| `PATCH` | `/questions/{id}` | speaker | Mark as answered: `{"answered": true}` | `200` |
| `DELETE` | `/questions/{id}` | speaker | Delete a question and its votes | `204` |

Send the token as `Authorization: Bearer <token>` (in `/docs`, use the **Authorize** button).

Errors: `401` not logged in or wrong password, `403` logged in but not the speaker, `404` no such question, `422` invalid input, `429` too many requests (wait `Retry-After` seconds). Responses never include `author_email` or who voted.

## Settings

| Variable | Default | Meaning |
|---|---|---|
| `ASKBOARD_STORAGE` | `memory` | `memory` or `sqlite` |
| `ASKBOARD_DB` | `askboard.db` | SQLite file, when `ASKBOARD_STORAGE=sqlite` |
| `ASKBOARD_SPEAKER_PASSWORD` | `speaker` | Password that gives the speaker role |
| `ASKBOARD_RATE_LIMIT` / `ASKBOARD_RATE_WINDOW` | `10` / `10` | At most 10 writes (asks + votes) per user every 10 seconds |

Login tokens and rate-limit counters are kept in memory, so after a restart everyone logs in again (the board does this by itself).
