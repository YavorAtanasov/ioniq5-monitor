from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..deps import CurrentUser, DbSession
from ..models import Agent, EnrollmentCode, User, Vehicle
from ..schemas import (
    AgentResponse,
    EnrollmentCodeResponse,
    VehicleCreate,
    VehicleResponse,
)
from ..security import generate_enrollment_code, hash_enrollment_code

router = APIRouter(prefix="/v1/vehicles", tags=["vehicles"])


def _owned_vehicle(vehicle_id: str, user: User, db: Session) -> Vehicle:
    vehicle = db.scalar(
        select(Vehicle).where(Vehicle.id == vehicle_id, Vehicle.org_id == user.org_id)
    )
    if vehicle is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle not found"
        )
    return vehicle


@router.post("", response_model=VehicleResponse, status_code=status.HTTP_201_CREATED)
def create_vehicle(payload: VehicleCreate, user: CurrentUser, db: DbSession) -> Vehicle:
    vehicle = Vehicle(org_id=user.org_id, name=payload.name)
    db.add(vehicle)
    db.commit()
    return vehicle


@router.get("", response_model=list[VehicleResponse])
def list_vehicles(user: CurrentUser, db: DbSession) -> list[Vehicle]:
    return list(
        db.scalars(
            select(Vehicle)
            .where(Vehicle.org_id == user.org_id)
            .order_by(Vehicle.created_at)
        )
    )


@router.post(
    "/{vehicle_id}/enrollment-codes",
    response_model=EnrollmentCodeResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_enrollment_code(
    vehicle_id: str, user: CurrentUser, db: DbSession
) -> EnrollmentCodeResponse:
    vehicle = _owned_vehicle(vehicle_id, user, db)
    code = generate_enrollment_code()
    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=get_settings().enrollment_code_ttl_minutes
    )
    db.add(
        EnrollmentCode(
            org_id=user.org_id,
            vehicle_id=vehicle.id,
            code_hash=hash_enrollment_code(code),
            expires_at=expires_at,
        )
    )
    db.commit()
    return EnrollmentCodeResponse(
        code=code, vehicle_id=vehicle.id, expires_at=expires_at
    )


@router.get("/{vehicle_id}/agents", response_model=list[AgentResponse])
def list_agents(vehicle_id: str, user: CurrentUser, db: DbSession) -> list[Agent]:
    vehicle = _owned_vehicle(vehicle_id, user, db)
    return list(
        db.scalars(
            select(Agent)
            .where(Agent.vehicle_id == vehicle.id)
            .order_by(Agent.created_at)
        )
    )


@router.delete(
    "/{vehicle_id}/agents/{agent_id}", status_code=status.HTTP_204_NO_CONTENT
)
def revoke_agent(
    vehicle_id: str, agent_id: str, user: CurrentUser, db: DbSession
) -> None:
    vehicle = _owned_vehicle(vehicle_id, user, db)
    agent = db.scalar(
        select(Agent).where(Agent.id == agent_id, Agent.vehicle_id == vehicle.id)
    )
    if agent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found"
        )
    agent.revoked_at = datetime.now(timezone.utc)
    db.commit()
