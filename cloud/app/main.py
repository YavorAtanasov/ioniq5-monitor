from contextlib import asynccontextmanager

from fastapi import FastAPI

from .db import init_db
from .routers import agents, auth, ingest, series, vehicles


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Ioniq5 Monitor Cloud",
    description=(
        "Ingest and query API for the hosted dashboard. Vehicle credentials stay "
        "on the owner's own agent; this service only ever sees readings."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(auth.router)
app.include_router(vehicles.router)
app.include_router(agents.router)
app.include_router(ingest.router)
app.include_router(series.router)


@app.get("/healthz", tags=["ops"])
def healthz() -> dict[str, str]:
    return {"status": "ok"}
