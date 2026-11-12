"""HTTP layer (presentation): URLs, methods, status codes and models.

Each route translates HTTP into a call to the store and back.
Who may do what:
- reading is public (and cached with ETags),
- asking and voting need a logged-in user (and are rate limited),
- marking answered and deleting are for the speaker only.
"""

from fastapi import APIRouter, HTTPException, Query, Request, status

from askboard.auth import Speaker
from askboard.cache import json_with_etag
from askboard.models import QuestionIn, QuestionOut, QuestionUpdate
from askboard.rate_limit import LimitedUser
from askboard.storage import QuestionStore, SortOrder, make_store

store: QuestionStore = make_store()

router = APIRouter(prefix="/questions", tags=["questions"])

NOT_FOUND = "Question not found"


def found(question):
    if question is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    return question


@router.post("", status_code=status.HTTP_201_CREATED, response_model=QuestionOut)
def ask_question(body: QuestionIn, user: LimitedUser):
    return store.add(body.text, user.name, body.author_email)


@router.get("", response_model=list[QuestionOut])
def read_questions(
    request: Request,
    sort: SortOrder = "recent",
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    answered: bool | None = None,
):
    questions = store.list(sort, limit, offset, answered)
    return json_with_etag(request, [QuestionOut.model_validate(q) for q in questions])


@router.get("/{question_id}", response_model=QuestionOut)
def read_question(question_id: int, request: Request):
    question = found(store.get(question_id))
    return json_with_etag(request, QuestionOut.model_validate(question))


@router.put("/{question_id}/vote", response_model=QuestionOut)
def vote(question_id: int, user: LimitedUser):
    return found(store.vote(question_id, user.name))


@router.patch("/{question_id}", response_model=QuestionOut)
def update_question(question_id: int, body: QuestionUpdate, _: Speaker):
    return found(store.set_answered(question_id, body.answered))


@router.delete("/{question_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_question(question_id: int, _: Speaker):
    if not store.delete(question_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
