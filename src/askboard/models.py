"""API models: what clients send (In / Update) and what they get back (Out)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Role = Literal["audience", "speaker"]


class LoginIn(BaseModel):
    """Body of POST /login. No password: audience. Speaker password: speaker."""

    name: str = Field(min_length=1, max_length=40)
    password: str | None = None


class TokenOut(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    name: str
    role: Role


class QuestionIn(BaseModel):
    """Body of POST /questions. The author is the logged-in user."""

    text: str = Field(min_length=3, max_length=280)
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
