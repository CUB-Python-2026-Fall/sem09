"""Application entry point: creates the FastAPI app and wires the parts together.

Run (from the sem09 folder):
    uv run uvicorn askboard.main:app --reload                         # in memory
    ASKBOARD_STORAGE=sqlite uv run uvicorn askboard.main:app --reload # SQLite file
"""

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from askboard import auth, routes

BOARD_PAGE = Path(__file__).parent / "static" / "board.html"

log = logging.getLogger("uvicorn.error")


def _arg(name: str, default: str) -> str:
    """Read --host / --port from the uvicorn command line (best effort)."""
    for i, a in enumerate(sys.argv):
        if a == name and i + 1 < len(sys.argv):
            return sys.argv[i + 1]
        if a.startswith(name + "="):
            return a.split("=", 1)[1]
    return default


@asynccontextmanager
async def lifespan(_app: FastAPI):
    base = f"http://{_arg('--host', '127.0.0.1')}:{_arg('--port', '8000')}"
    log.info("Client page: %s/board  |  API docs: %s/docs", base, base)
    yield


app = FastAPI(title="AskBoard", lifespan=lifespan)
app.include_router(auth.router)
app.include_router(routes.router)


@app.get("/board", include_in_schema=False)
def board():
    """The demo page: lists the questions and calls the API."""
    return FileResponse(BOARD_PAGE)
