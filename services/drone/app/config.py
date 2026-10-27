from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    drone_backend: str = "mock"  # mock | px4
    drone_count: int = 1

    # The plant helipad - Cernavodă NPP geography.
    home_lat: float = 44.3222
    home_lon: float = 28.0553
    home_alt: float = 25.0

    # px4 backend only: where MAVLink should be forwarded
    c2_host: str = "c2"
    px4_mavlink_base_port: int = 14540


settings = Settings()
