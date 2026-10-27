from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, sourced from environment variables / .env."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ── Database ──────────────────────────────────────────
    # Local sqlite by default; docker-compose overrides with Postgres.
    database_url: str = "sqlite+aiosqlite:///./c2.db"

    # ── Auth / JWT ────────────────────────────────────────
    # DELIBERATE LAB WEAKNESS: a guessable secret, so tools/exploit.py
    # jwtforge can crack it and forge an admin token.
    jwt_secret: str = "dev-insecure-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 720

    # ── Seed accounts ─────────────────────────────────────
    # DELIBERATE LAB WEAKNESS: known credentials, re-asserted every boot,
    # so exploit.py brute can guess them.
    admin_username: str = "admin"
    admin_password: str = "Admin1Admin1"

    # Non-admin demo accounts: an operator (can fly) and an observer (read-only).
    seed_demo_users: bool = True
    operator_username: str = "operator"
    operator_password: str = "Admin1Admin1"
    observer_username: str = "observer"
    observer_password: str = "Admin1Admin1"

    # ── Drone integration ─────────────────────────────────
    drone_backend: str = "mock"  # mock | px4
    drone_api_url: str = "http://localhost:9100"
    drone_ws_url: str = "ws://localhost:9100/ws"
    drone_mavlink_port: int = 14540
    drone_count: int = 1

    # ── Auto-patrol on startup ────────────────────────────
    # When true, every drone is powered on and put on patrol at startup.
    auto_patrol: bool = True
    auto_patrol_route: str = "perimeter"   # a key of site.PATROL_ROUTES
    auto_patrol_alt: float = 60.0          # metres AGL; clears structures on the route

    # ── Home position (the drone spawns here; the map centers here) ──
    # Home comes from the site's launch pads; these remain for the drone
    # service's initial registry, which the C2 relocates on power-on.
    home_lat: float = 43.9977991   # HP-1
    home_lon: float = 25.0154851
    home_alt: float = 95.0

    # ── Multi-operator claim/lock ─────────────────────────
    claim_ttl_seconds: int = 120

    # ── IDS alert ingestion (sensor -> C2 -> operators over /ws) ─────
    # DELIBERATE LAB WEAKNESS: a shared static token, not a JWT, so forged
    # alerts can be pushed. See app/services/ids.py.
    ids_push_token: str = "ids-dev-token"
    # The C2 proxies the sensor's flow records; alerts arrive by push.
    sensor_url: str = "http://sensor:9200"
    ids_buffer_size: int = 500

    # ── CORS ──────────────────────────────────────────────
    cors_origins: str = "http://localhost:5173,http://localhost:8080"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
