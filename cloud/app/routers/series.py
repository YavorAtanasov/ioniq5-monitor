from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from ..deps import CurrentUser, DbSession
from ..models import Reading, Vehicle
from ..schemas import SeriesPoint, SeriesResponse

router = APIRouter(prefix="/v1/vehicles", tags=["series"])


@router.get("/{vehicle_id}/series", response_model=SeriesResponse)
def get_series(
    vehicle_id: str,
    measurement: str,
    user: CurrentUser,
    db: DbSession,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=10000)] = 1000,
) -> SeriesResponse:
    vehicle = db.scalar(
        select(Vehicle).where(Vehicle.id == vehicle_id, Vehicle.org_id == user.org_id)
    )
    if vehicle is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle not found"
        )

    # org_id is filtered on as well as vehicle_id: belt and braces, so a bug in
    # ownership checking still can't leak another tenant's series.
    query = select(Reading).where(
        Reading.org_id == user.org_id,
        Reading.vehicle_id == vehicle.id,
        Reading.measurement == measurement,
    )
    if since is not None:
        query = query.where(Reading.ts >= since)
    if until is not None:
        query = query.where(Reading.ts <= until)

    rows = db.scalars(query.order_by(Reading.ts).limit(limit))
    return SeriesResponse(
        vehicle_id=vehicle.id,
        measurement=measurement,
        points=[
            SeriesPoint(timestamp=r.ts, tags=r.tags, fields=r.fields) for r in rows
        ],
    )
