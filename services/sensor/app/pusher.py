from __future__ import annotations

import asyncio
import logging

import httpx

from app.config import Settings
from app.models import Alert

logger = logging.getLogger("sensor.pusher")


class AlertPusher:
    """Pushes alerts to the C2's `POST /api/ids/alerts` with exponential backoff.

    After `push_max_retries` the alert is dropped; it stays available via this
    sensor's /alerts and /ws.
    """

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._client = client or httpx.AsyncClient(timeout=settings.push_timeout)
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def push(self, alert: Alert) -> bool:
        """Push one alert. True if the C2 accepted it, False once retries are exhausted."""
        url = f"{self._settings.c2_url}/api/ids/alerts"
        headers = {"X-IDS-Token": self._settings.ids_push_token}
        body = alert.model_dump()

        delay = self._settings.push_base_delay
        last_error: str | None = None

        for attempt in range(1, self._settings.push_max_retries + 1):
            try:
                resp = await self._client.post(url, json=body, headers=headers)
                if resp.status_code < 300:
                    return True
                if resp.status_code == 404:
                    last_error = "404 (C2 ingestion endpoint not available yet)"
                else:
                    last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
            except httpx.HTTPError as exc:
                last_error = f"{type(exc).__name__}: {exc}"

            logger.warning(
                "pusher: attempt %d/%d failed pushing sid=%s to %s: %s",
                attempt, self._settings.push_max_retries, alert.sid, url, last_error,
            )
            if attempt < self._settings.push_max_retries:
                await asyncio.sleep(min(delay, self._settings.push_max_delay))
                delay *= 2

        logger.error(
            "pusher: giving up on sid=%s after %d attempts (last error: %s) - "
            "alert remains available via this sensor's own /alerts API",
            alert.sid, self._settings.push_max_retries, last_error,
        )
        return False
