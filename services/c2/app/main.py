from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import audit, auth, drones, ids, missions, public, siteobjects, users, ws
from app.config import settings
from app.db.base import init_db
from app.seed import seed
from app.services.fleet import fleet


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await seed()
    await fleet.startup()
    try:
        yield
    finally:
        await fleet.shutdown()


app = FastAPI(title="Drone C2", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for module in (auth, users, drones, missions, audit, ids, siteobjects, public, ws):
    app.include_router(module.router)


@app.get("/health", tags=["health"])
async def health() -> dict:
    return {"status": "ok", "drone_backend": settings.drone_backend}
