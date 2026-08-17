from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=200)
    org_name: str = Field(default="My garage", max_length=200)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class VehicleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class VehicleResponse(BaseModel):
    id: str
    name: str
    created_at: datetime


class EnrollmentCodeResponse(BaseModel):
    code: str
    vehicle_id: str
    expires_at: datetime


class EnrollRequest(BaseModel):
    code: str
    agent_name: str = Field(default="poller", max_length=200)


class EnrollResponse(BaseModel):
    """The API key is returned exactly once; only its hash is stored."""

    agent_id: str
    vehicle_id: str
    api_key: str


class AgentResponse(BaseModel):
    id: str
    name: str
    vehicle_id: str
    key_prefix: str
    created_at: datetime
    last_seen_at: datetime | None
    revoked_at: datetime | None


class ReadingIn(BaseModel):
    measurement: str = Field(min_length=1, max_length=100)
    timestamp: datetime
    fields: dict[str, float | bool | str] = Field(default_factory=dict)
    tags: dict[str, str] = Field(default_factory=dict)
    # Accepted for wire compatibility with the self-hosted poller, which tags
    # points with a VIN. Deliberately ignored: the vehicle is derived from the
    # agent's key so one tenant can never write into another's series.
    vehicle: str | None = None


class IngestRequest(BaseModel):
    readings: list[ReadingIn] = Field(min_length=1, max_length=1000)


class IngestResponse(BaseModel):
    accepted: int
    updated: int
    rejected: int


class SeriesPoint(BaseModel):
    timestamp: datetime
    tags: dict[str, str]
    fields: dict[str, float | bool | str]


class SeriesResponse(BaseModel):
    vehicle_id: str
    measurement: str
    points: list[SeriesPoint]
