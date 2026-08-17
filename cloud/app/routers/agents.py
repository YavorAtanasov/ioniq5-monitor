from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from ..deps import DbSession
from ..models import Agent, EnrollmentCode
from ..schemas import EnrollRequest, EnrollResponse
from ..security import (
    AGENT_KEY_PREFIX,
    generate_agent_key,
    hash_agent_key,
    hash_enrollment_code,
)

router = APIRouter(prefix="/v1/agents", tags=["agents"])


@router.post(
    "/enroll", response_model=EnrollResponse, status_code=status.HTTP_201_CREATED
)
def enroll(payload: EnrollRequest, db: DbSession) -> EnrollResponse:
    """Trade a one-time enrollment code for a long-lived agent API key."""
    code = db.scalar(
        select(EnrollmentCode).where(
            EnrollmentCode.code_hash == hash_enrollment_code(payload.code)
        )
    )
    now = datetime.now(timezone.utc)
    if code is None or code.used_at is not None or _expired(code, now):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Enrollment code is invalid, already used, or expired",
        )

    api_key = generate_agent_key()
    agent = Agent(
        org_id=code.org_id,
        vehicle_id=code.vehicle_id,
        name=payload.agent_name,
        key_prefix=api_key[: len(AGENT_KEY_PREFIX) + 6],
        key_hash=hash_agent_key(api_key),
    )
    code.used_at = now
    db.add(agent)
    db.commit()
    return EnrollResponse(
        agent_id=agent.id, vehicle_id=agent.vehicle_id, api_key=api_key
    )


def _expired(code: EnrollmentCode, now: datetime) -> bool:
    expires_at = code.expires_at
    if expires_at.tzinfo is None:  # SQLite round-trips datetimes without tzinfo
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at < now
