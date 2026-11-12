"""Application entry point: creates the FastAPI app and wires the parts together.

Run (from the sem09 folder):
    uv run uvicorn askboard.main:app --reload                         # in memory
    ASKBOARD_STORAGE=sqlite uv run uvicorn askboard.main:app --reload # SQLite file
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from askboard import routes

BOARD_PAGE = Path(__file__).parent / "static" / "board.html"

app = FastAPI(title="AskBoard")
app.include_router(routes.router)


@app.get("/board", include_in_schema=False)
def board():
    """The demo page: lists the questions and calls the API."""
    return FileResponse(BOARD_PAGE)
