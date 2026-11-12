"""HTTP layer (presentation): URLs, methods, status codes and models.

Each route translates HTTP into a call to the store and back.
"""

from fastapi import APIRouter, HTTPException, Query, status

from askboard.models import QuestionIn, QuestionOut, QuestionUpdate
from askboard.storage import QuestionStore, SortOrder, make_store

store: QuestionStore = make_store()

router = APIRouter(prefix="/questions", tags=["questions"])

NOT_FOUND = "Question not found"


def found(question):
    if question is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    return question


@router.post("", status_code=status.HTTP_201_CREATED, response_model=QuestionOut)
def ask_question(body: QuestionIn):
    return store.add(body.text, body.author, body.author_email)


@router.get("", response_model=list[QuestionOut])
def read_questions(
    sort: SortOrder = "recent",
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    answered: bool | None = None,
):
    return store.list(sort, limit, offset, answered)


@router.get("/{question_id}", response_model=QuestionOut)
def read_question(question_id: int):
    return found(store.get(question_id))


@router.put("/{question_id}/votes/{user}", response_model=QuestionOut)
def vote(question_id: int, user: str):
    """PUT, not POST: "user X has voted for question Y" is a state, so
    repeating the request is harmless (idempotent)."""
    return found(store.vote(question_id, user))


@router.patch("/{question_id}", response_model=QuestionOut)
def update_question(question_id: int, body: QuestionUpdate):
    return found(store.set_answered(question_id, body.answered))


@router.delete("/{question_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_question(question_id: int):
    if not store.delete(question_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
