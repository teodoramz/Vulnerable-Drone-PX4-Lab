from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TelemetrySample(Base):
    """Low-rate persisted telemetry, for track history / after-action review."""

    __tablename__ = "telemetry_samples"

    id: Mapped[int] = mapped_column(primary_key=True)
    drone_id: Mapped[int] = mapped_column(Integer, index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    alt: Mapped[float] = mapped_column(Float)
    heading: Mapped[float] = mapped_column(Float, default=0.0)
    state: Mapped[str] = mapped_column(String(16), default="")
