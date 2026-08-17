from datetime import datetime, timezone
from typing import Annotated

import jwt
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db
from .models import Agent, User
from .security import decode_access_token, hash_agent_key

DbSession = Annotated[Session, Depends(get_db)]
AuthHeader = Annotated[str | None, Header(alias="Authorization")]


def _bearer_token(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return authorization.split(" ", 1)[1].strip()


def current_user(db: DbSession, authorization: AuthHeader = None) -> User:
    token = _bearer_token(authorization)
    try:
        payload = decode_access_token(token)
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        )

    user = db.get(User, payload.get("sub"))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        )
    return user


def current_agent(db: DbSession, authorization: AuthHeader = None) -> Agent:
    key = _bearer_token(authorization)
    agent = db.scalar(select(Agent).where(Agent.key_hash == hash_agent_key(key)))
    if agent is None or agent.revoked_at is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid agent key"
        )

    agent.last_seen_at = datetime.now(timezone.utc)
    db.commit()
    return agent


CurrentUser = Annotated[User, Depends(current_user)]
CurrentAgent = Annotated[Agent, Depends(current_agent)]
