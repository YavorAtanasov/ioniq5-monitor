# Cloud API

The hosted half of the product. It stores readings and serves them back per
tenant; it never sees a Bluelink username, password or PIN, because the poller
that holds those keeps running on the vehicle owner's own hardware and pushes
readings here over an API key.

```
owner's Pi                                    your servers
┌───────────────────────────┐                 ┌──────────────────────┐
│ poller + .env credentials │──readings only─▶│ cloud API → Postgres │
│ InfluxDB + Grafana (opt.) │   agent API key └──────────────────────┘
└───────────────────────────┘
```

## Running it

```bash
cp cloud/.env.example cloud/.env   # then set CLOUD_JWT_SECRET and CLOUD_API_KEY_PEPPER
docker compose -f docker-compose.cloud.yml up -d
open http://localhost:8000/docs
```

## Onboarding an owner

1. `POST /v1/auth/signup` — creates an org and its first user, returns a JWT.
2. `POST /v1/vehicles` — one row per car.
3. `POST /v1/vehicles/{id}/enrollment-codes` — a single-use code, valid one hour.
4. On the owner's Pi: `python poller/enroll.py --url https://your-api --code ABCD-EFGH-JKLM`.
   That trades the code for an agent API key and writes it into their `.env`.
5. The poller restarts and starts calling `POST /v1/ingest`; the dashboard reads
   `GET /v1/vehicles/{id}/series?measurement=vehicle_status`.

An owner can list and revoke agents at any time; revocation is immediate, since
ingest checks `revoked_at` on every request.

## Tenancy and ingest rules

- Every reading carries `org_id` **and** `vehicle_id`, both taken from the
  authenticated agent. The payload's `vehicle` field is accepted for wire
  compatibility with the self-hosted poller and deliberately ignored, so a
  compromised or buggy agent cannot write into another tenant's series.
- Reads filter on `org_id` as well as vehicle ownership.
- `(vehicle_id, measurement, ts, tags_key)` is unique, so an agent replaying its
  offline spool updates points instead of duplicating them.
- Timestamps more than `CLOUD_MAX_FUTURE_SKEW_MINUTES` ahead are rejected -
  that's a clock-skewed agent, not data.

## Not built yet

Billing, a web frontend, password reset, email verification, rate limiting per
agent, and per-tenant retention/export (GDPR). Schema changes are currently
applied with `Base.metadata.create_all` at startup; that needs to become Alembic
migrations before this holds data anyone cares about.
