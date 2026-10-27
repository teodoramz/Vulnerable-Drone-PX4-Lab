from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Sensor sidecar settings, read from environment variables / .env."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ── Capture interfaces ────────────────────────────────────────────
    # Comma-separated. entrypoint.sh builds the af-packet arguments from it; the
    # sidecar uses it for /health and as the fallback `iface` on eve records.
    sensor_ifaces: str = "ot-ops,ot-air"

    # ── Suricata eve.json ─────────────────────────────────────────────
    eve_path: str = "/var/log/suricata/eve.json"
    # Tailer poll interval (seconds) once caught up.
    eve_poll_interval: float = 0.5

    # ── C2 alert push ──────────────────────────────────────────────────
    c2_url: str = "http://c2:8000"
    ids_push_token: str = "ids-dev-token"
    # Capped retry/backoff for C2 pushes; alerts are dropped after the last retry.
    # The sensor's own /alerts API stays the out-of-band source of truth.
    push_max_retries: int = 5
    push_base_delay: float = 0.5
    push_max_delay: float = 8.0
    push_timeout: float = 5.0

    # ── Ring buffers ──────────────────────────────────────────────────
    alert_buffer_size: int = 2000
    flow_buffer_size: int = 2000

    @property
    def iface_list(self) -> list[str]:
        return [i.strip() for i in self.sensor_ifaces.split(",") if i.strip()]


settings = Settings()
