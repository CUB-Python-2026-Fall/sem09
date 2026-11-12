"""Notebook-only tools for sem09_askboard.ipynb.

None of this is part of the app. It lets the notebook:
- run the app with uvicorn in a background thread, the same server as
  `uvicorn askboard.main:app`, while cells keep adding routes to it;
- replace a route when a cell defines it again (like editing the file
  and letting `--reload` restart the server);
- send requests and print them (`show`), and simulate an audience.
"""

import json
import random
import threading
import time
from collections import Counter

import httpx
import uvicorn
from fastapi import FastAPI
from fastapi.routing import APIRoute

HOST, PORT = "127.0.0.1", 8000
client = httpx.Client(base_url=f"http://{HOST}:{PORT}")
_app: FastAPI | None = None


# --- Running the app -------------------------------------------------------


def _is_route(route, method, path):
    return isinstance(route, APIRoute) and route.path == path and method in route.methods


def _live_reload(app: FastAPI) -> None:
    """A route defined again replaces the old one (same function name, or same
    method and path), and /docs and the board see new routes at once."""
    add_api_route = app.router.add_api_route

    def add_or_replace(path, endpoint, *, methods=None, **kwargs):
        methods = [m.upper() for m in methods or ["GET"]]
        name = kwargs.get("name") or endpoint.__name__
        app.router.routes = [
            r for r in app.router.routes
            if not (isinstance(r, APIRoute) and (r.name == name or any(_is_route(r, m, path) for m in methods)))
        ]
        add_api_route(path, endpoint, methods=methods, **kwargs)

    def fresh_openapi():
        app.openapi_schema = None
        return FastAPI.openapi(app)

    app.router.add_api_route = add_or_replace
    app.openapi = fresh_openapi


def run_in_background(app: FastAPI) -> None:
    """Start uvicorn for `app` in a background thread."""
    global _app
    _app = app
    _live_reload(app)
    server = uvicorn.Server(uvicorn.Config(app, host=HOST, port=PORT, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    while not server.started:
        time.sleep(0.05)
    print(f"Server running at http://{HOST}:{PORT}")
    print(f"Client:            http://{HOST}:{PORT}/board")


def has_route(method, path):
    return _app is not None and any(_is_route(r, method, path) for r in _app.routes)


# --- Printing requests -----------------------------------------------------


def _shorten(data, limit=80):
    """Long strings are cut when printed."""
    if isinstance(data, str) and len(data) > limit:
        return f"{data[:limit]}... ({len(data)} characters)"
    if isinstance(data, dict):
        return {k: _shorten(v, limit) for k, v in data.items()}
    if isinstance(data, list):
        return [_shorten(v, limit) for v in data]
    return data


def show(response: httpx.Response, headers=()):
    """Print the request (and its body), then the status and the JSON response."""
    request = response.request
    print(f"{request.method} {request.url.raw_path.decode()}")
    if request.content:
        print(json.dumps(_shorten(json.loads(request.content)), indent=2, ensure_ascii=False))
    print(f"-> {response.status_code} {response.reason_phrase}")
    for name in headers:
        if name in response.headers:
            print(f"   {name}: {response.headers[name]}")
    if response.content:
        print(json.dumps(_shorten(response.json()), indent=2, ensure_ascii=False))
    print()


def token_for(name, password=None):
    """Log in and return the header to send with each request."""
    response = client.post("/login", json={"name": name, "password": password})
    return {"Authorization": "Bearer " + response.json()["access_token"]}


# --- A simulated audience --------------------------------------------------

SAMPLE_QUESTIONS = [
    "What is the difference between PUT and PATCH?",
    "Should every endpoint return JSON?",
    "How do I version an API?",
    "When should I use async def?",
    "How do I test an API?",
    "What does stateless mean?",
    "Why is my 204 response empty?",
    "What goes in the URL and what goes in the body?",
]
PEOPLE = ["ana", "ben", "carla", "dan", "eva", "finn", "gina", "hugo"]
_tokens: dict[str, dict] = {}
_rng = random.Random(7)


def _auth(person):
    if not has_route("POST", "/login"):
        return {}
    if person not in _tokens:
        _tokens[person] = token_for(person)
    return _tokens[person]


def _ask(person, text):
    body = {"text": text} if has_route("POST", "/login") else {"text": text, "author": person}
    return client.post("/questions", json=body, headers=_auth(person))


def _vote(person, question_id):
    if has_route("PUT", "/questions/{question_id}/vote"):
        return client.put(f"/questions/{question_id}/vote", headers=_auth(person))
    return client.put(f"/questions/{question_id}/votes/{person}")


def simulate_users(questions=0, votes=0, spam=0):
    """Post sample questions, cast random votes, or have one person vote `spam` times in a row."""
    _tokens.clear()  # log in again, in case the server forgot us
    statuses = Counter()
    for _ in range(questions):
        statuses[_ask(_rng.choice(PEOPLE), _rng.choice(SAMPLE_QUESTIONS)).status_code] += 1
    ids = [q["id"] for q in client.get("/questions").json()] if votes or spam else []
    for _ in range(votes):
        statuses[_vote(_rng.choice(PEOPLE), _rng.choice(ids)).status_code] += 1
    for _ in range(spam):
        statuses[_vote("ben", ids[0]).status_code] += 1
    print("Status codes:", dict(statuses))
