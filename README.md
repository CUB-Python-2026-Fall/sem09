# AskBoard

A live Q&A board API: people post questions and upvote them, and the speaker marks them as answered. Built with FastAPI. Data is kept in memory by default, or in SQLite (the standard library `sqlite3` module, no ORM).

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
  main.py        creates the app: adds the routes and the /board page
  routes.py      HTTP layer for /questions: URLs, methods, status codes
  models.py      Pydantic API models: QuestionIn, QuestionUpdate, QuestionOut
  storage.py     QuestionStore (a Protocol), the Question record, and two stores:
                 InMemoryQuestionStore and SQLiteQuestionStore (all the SQL lives here);
                 make_store() picks one from config
  database.py    SQLite connection (one transaction per call) and the schema
  config.py      settings from environment variables
  static/board.html   the demo page; it only calls the API
tests/
  test_api.py
```

Each layer only talks to the one below it: `routes` → `storage` → `database`. The routes only know the `QuestionStore` protocol (the store is created once from config, in `routes.store`), so either store can be plugged in without touching them, and the stores never see HTTP. The tests run against both stores.

## API

| Method | URL | What it does | Success |
|---|---|---|---|
| `POST` | `/questions` | Ask a question (`text`, `author`, `author_email`) | `201` |
| `GET` | `/questions?sort=votes&limit=20&offset=0&answered=false` | List questions. `sort` is `recent` (default) or `votes` | `200` |
| `GET` | `/questions/{id}` | One question | `200` |
| `PUT` | `/questions/{id}/votes/{user}` | Vote. One vote per user; repeating it changes nothing | `200` |
| `PATCH` | `/questions/{id}` | Mark as answered: `{"answered": true}` | `200` |
| `DELETE` | `/questions/{id}` | Delete a question and its votes | `204` |

A missing question is `404`; invalid input is `422`. Responses never include `author_email` or who voted.

## Settings

| Variable | Default | Meaning |
|---|---|---|
| `ASKBOARD_STORAGE` | `memory` | `memory` or `sqlite` |
| `ASKBOARD_DB` | `askboard.db` | SQLite file, when `ASKBOARD_STORAGE=sqlite` |
