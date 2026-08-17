import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter
from sqlalchemy import select

from ..config import get_settings
from ..deps import CurrentAgent, DbSession
from ..models import Agent, Reading
from ..schemas import IngestRequest, IngestResponse, ReadingIn

router = APIRouter(prefix="/v1", tags=["ingest"])


def tags_key(tags: dict[str, str]) -> str:
    return json.dumps(tags, sort_keys=True, separators=(",", ":"))


def _normalise_ts(ts: datetime) -> datetime:
    return ts.astimezone(timezone.utc) if ts.tzinfo else ts.replace(tzinfo=timezone.utc)


@router.post("/ingest", response_model=IngestResponse)
def ingest(
    payload: IngestRequest, agent: CurrentAgent, db: DbSession
) -> IngestResponse:
    """Accept a batch of readings from an owner's on-premise agent.

    Re-sending a reading updates it rather than duplicating it, so an agent
    replaying its offline spool after a network outage is always safe.
    """
    settings = get_settings()
    horizon = datetime.now(timezone.utc) + timedelta(
        minutes=settings.max_future_skew_minutes
    )
    accepted = updated = rejected = 0

    for item in payload.readings:
        ts = _normalise_ts(item.timestamp)
        if ts > horizon:
            rejected += 1
            continue

        key = tags_key(item.tags)
        existing = db.scalar(
            select(Reading).where(
                Reading.vehicle_id == agent.vehicle_id,
                Reading.measurement == item.measurement,
                Reading.ts == ts,
                Reading.tags_key == key,
            )
        )
        if existing is not None:
            existing.fields = item.fields
            updated += 1
        else:
            db.add(_new_reading(agent, item, ts, key))
            accepted += 1

    db.commit()
    return IngestResponse(accepted=accepted, updated=updated, rejected=rejected)


def _new_reading(agent: Agent, item: ReadingIn, ts: datetime, key: str) -> Reading:
    return Reading(
        org_id=agent.org_id,
        vehicle_id=agent.vehicle_id,
        measurement=item.measurement,
        ts=ts,
        tags_key=key,
        tags=item.tags,
        fields=item.fields,
    )
