"""API models: what clients send (In / Update) and what they get back (Out)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class QuestionIn(BaseModel):
    """Body of POST /questions."""

    text: str = Field(min_length=3, max_length=280)
    author: str = Field("anonymous", min_length=1, max_length=40)
    author_email: str | None = None


class QuestionUpdate(BaseModel):
    """Body of PATCH /questions/{question_id}."""

    answered: bool


class QuestionOut(BaseModel):
    """A question as clients see it: author_email stays on the server."""

    model_config = ConfigDict(from_attributes=True)  # built from a storage.Question

    id: int
    text: str
    author: str
    votes: int
    answered: bool
    created_at: datetime
