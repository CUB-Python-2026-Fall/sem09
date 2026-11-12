"""Minimal authentication: log in once, then send the token on every request.

    POST /login  {"name": "ana"}                         -> audience token
    POST /login  {"name": "eva", "password": "<speaker>"} -> speaker token
    then:        Authorization: Bearer <token>

Tokens are lost on restart
"""

import secrets
from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from askboard import config
from askboard.models import LoginIn, Role, TokenOut


@dataclass(frozen=True)
class User:
    name: str
    role: Role


# token -> user
sessions: dict[str, User] = {}

router = APIRouter(tags=["auth"])


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn):
    if body.password is None:
        role: Role = "audience"
    elif secrets.compare_digest(body.password, config.SPEAKER_PASSWORD):
        role = "speaker"
    else:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong password")
    token = secrets.token_urlsafe(24)
    sessions[token] = User(body.name, role)
    return TokenOut(access_token=token, name=body.name, role=role)


bearer = HTTPBearer(auto_error=False)  # we raise our own 401 below


def current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> User:
    """401 Unauthorized: we don't know who you are."""
    user = sessions.get(credentials.credentials) if credentials else None
    if user is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Not logged in",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def speaker(user: Annotated[User, Depends(current_user)]) -> User:
    """403 Forbidden: we know who you are, but you are not allowed to do this."""
    if user.role != "speaker":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the speaker can do this")
    return user


CurrentUser = Annotated[User, Depends(current_user)]
Speaker = Annotated[User, Depends(speaker)]
