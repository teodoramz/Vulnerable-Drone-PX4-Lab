from __future__ import annotations

from sqlalchemy import func, select

from app.config import settings
from app.core.rbac import Role
from app.core.security import hash_password
from app.db.base import AsyncSessionLocal
from app.models.drone import Drone
from app.models.user import User
from app.services import site

_CALLSIGNS = ["Sentinel", "Vigil", "Warden", "Aegis", "Lookout", "Guardian", "Beacon", "Watchman"]


async def seed() -> None:
    """Idempotently create the admin, demo users and drone registry; config wins on every boot."""
    async with AsyncSessionLocal() as session:
        admin = (
            await session.execute(select(User).where(User.username == settings.admin_username))
        ).scalar_one_or_none()
        if admin is None:
            session.add(User(
                username=settings.admin_username,
                hashed_password=hash_password(settings.admin_password),
                role=Role.admin,
                is_active=True,
            ))
        else:
            # Configuration is authoritative: re-assert credentials on every boot.
            admin.hashed_password = hash_password(settings.admin_password)
            admin.role = Role.admin
            admin.is_active = True

        if settings.seed_demo_users:
            crew = (
                (settings.operator_username, settings.operator_password, Role.operator),
                (settings.observer_username, settings.observer_password, Role.observer),
            )
            for username, password, role in crew:
                existing = (
                    await session.execute(select(User).where(User.username == username))
                ).scalar_one_or_none()
                if existing is None:
                    session.add(User(
                        username=username,
                        hashed_password=hash_password(password),
                        role=role,
                        is_active=True,
                    ))
                else:
                    existing.hashed_password = hash_password(password)
                    existing.role = role
                    existing.is_active = True

        # Reconcile the registry with DRONE_COUNT.
        existing = {d.id: d for d in (await session.execute(select(Drone))).scalars()}

        # Drop surplus drones first, freeing their callsigns.
        for drone_id, drone in sorted(existing.items()):
            if drone_id >= settings.drone_count:
                await session.delete(drone)
        await session.flush()

        # Home comes from the launch pads; HOME_ALT is config (not in the dataset).
        pads = site.LAUNCH_PADS
        for i in range(settings.drone_count):
            callsign = _CALLSIGNS[i] if i < len(_CALLSIGNS) else f"Unit{i}"
            # Spread a swarm over the pads.
            home = pads[i % len(pads)]
            drone = existing.get(i)
            if drone is None:
                session.add(Drone(
                    id=i, callsign=callsign, model="x500",
                    home_lat=home["lat"],
                    home_lon=home["lon"],
                    home_alt=settings.home_alt,
                ))
            else:
                # Keep in sync with the dataset.
                drone.callsign = callsign
                drone.home_lat = home["lat"]
                drone.home_lon = home["lon"]
                drone.home_alt = settings.home_alt

        await session.commit()
