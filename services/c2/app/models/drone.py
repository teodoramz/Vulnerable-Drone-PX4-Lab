from __future__ import annotations

from sqlalchemy import Float, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Drone(Base):
    """Persistent drone registry. ``id`` matches the simulator's drone id."""

    __tablename__ = "drones"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    callsign: Mapped[str] = mapped_column(String(32), unique=True)
    model: Mapped[str] = mapped_column(String(32), default="x500")
    home_lat: Mapped[float] = mapped_column(Float, default=47.397742)
    home_lon: Mapped[float] = mapped_column(Float, default=8.545594)
    home_alt: Mapped[float] = mapped_column(Float, default=488.0)
