from __future__ import annotations

import httpx


class DroneClient:
    """HTTP client for the drone service's lifecycle API (mock and PX4 alike)."""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self._client: httpx.AsyncClient | None = None

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(base_url=self.base_url, timeout=10.0)
        return self._client

    async def health(self) -> dict:
        resp = await self._http().get("/health")
        resp.raise_for_status()
        return resp.json()

    async def list_drones(self) -> list[dict]:
        resp = await self._http().get("/drones")
        resp.raise_for_status()
        return resp.json()

    async def power(self, drone_id: int, on: bool,
                    home: tuple[float, float, float] | None = None) -> None:
        """Power a drone on or off, optionally relocating it to a pad first."""
        body: dict = {"on": on}
        if home is not None:
            body["home_lat"], body["home_lon"], body["home_alt"] = home
        resp = await self._http().post(f"/drones/{drone_id}/power", json=body)
        resp.raise_for_status()

    async def reset(self, drone_id: int) -> dict:
        """Maintenance reset on the drone service. Returns what it cleared."""
        resp = await self._http().post(f"/drones/{drone_id}/reset")
        resp.raise_for_status()
        return resp.json()

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
