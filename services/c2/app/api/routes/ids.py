from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from app.api.deps import get_current_user
from app.config import settings
from app.models.user import User
from app.schemas.ids import IdsAlertIn, IdsAlertOut
from app.services.ids import ids_service

router = APIRouter(prefix="/api/ids", tags=["ids"])


async def _verify_sensor(x_ids_token: str | None = Header(default=None)) -> None:
    """Sensor auth via a shared static token (not JWT); see app/services/ids.py for the trust tradeoff."""
    if not x_ids_token or x_ids_token != settings.ids_push_token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or missing X-IDS-Token")


@router.post("/alerts", status_code=status.HTTP_201_CREATED)
async def ingest_alert(alert: IdsAlertIn, _: None = Depends(_verify_sensor)) -> dict:
    """Ingestion endpoint the `sensor` service pushes Suricata alerts to."""
    await ids_service.ingest(alert)
    return {"status": "ok"}


@router.get("/alerts", response_model=list[IdsAlertOut])
async def list_alerts(
    _: User = Depends(get_current_user),
    limit: int = Query(default=100, le=500),
    severity: int | None = Query(default=None, ge=1, le=3),
):
    """Recent alerts; open to any authenticated user, observers included."""
    return ids_service.recent(limit=limit, severity=severity)


@router.get("/flows")
async def list_flows(
    _: User = Depends(get_current_user),
    limit: int = Query(default=100, le=500),
):
    """Recent flow records proxied from the sensor; an empty list with a flag if it is down."""
    url = f"{settings.sensor_url.rstrip('/')}/flows"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url, params={"limit": limit})
            resp.raise_for_status()
            return {"flows": resp.json(), "sensor_reachable": True}
    except Exception as exc:  # noqa: BLE001
        return {
            "flows": [],
            "sensor_reachable": False,
            "error": f"{type(exc).__name__}: {exc}",
            "sensor_url": url,
        }


@router.get("/live")
async def live_traffic(
    _: User = Depends(get_current_user),
    limit: int = Query(default=200, le=1000),
):
    """Live per-flow counters proxied from the sensor (the flow log only has ended flows)."""
    url = f"{settings.sensor_url.rstrip('/')}/live"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url, params={"limit": limit})
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:  # noqa: BLE001
        return {
            "available": False,
            "flows": [],
            "error": f"{type(exc).__name__}: {exc}",
            "sensor_url": url,
        }


async def _proxy(path: str, params: dict | None = None) -> dict:
    """GET from the sensor on the browser's behalf; degrades to a flagged error result."""
    url = f"{settings.sensor_url.rstrip('/')}{path}"
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(url, params=params or {})
            resp.raise_for_status()
            return {**resp.json(), "sensor_reachable": True}
    except Exception as exc:  # noqa: BLE001
        return {
            "sensor_reachable": False,
            "error": f"{type(exc).__name__}: {exc}",
            "sensor_url": url,
        }


@router.get("/packets")
async def recent_packets(
    _: User = Depends(get_current_user),
    limit: int = Query(default=200, le=1000),
    mavlink_only: bool = Query(default=False),
) -> dict:
    """Recent packets off the wire, with MAVLink message ids where present."""
    return await _proxy("/packets", {"limit": limit, "mavlink_only": mavlink_only})


@router.get("/breakdown")
async def traffic_breakdown(_: User = Depends(get_current_user)) -> dict:
    """Traffic totals by protocol and service port, plus the MAVLink mix."""
    return await _proxy("/breakdown")


@router.get("/captures")
async def list_captures(_: User = Depends(get_current_user)) -> dict:
    """The rotating packet captures on disk, as metadata."""
    return await _proxy("/captures")


@router.get("/captures/{name}")
async def download_capture(
    name: str,
    _: User = Depends(get_current_user),
) -> StreamingResponse:
    """Stream one capture file from the sensor (not buffered; captures are large)."""
    url = f"{settings.sensor_url.rstrip('/')}/captures/{name}"
    client = httpx.AsyncClient(timeout=None)
    try:
        req = client.build_request("GET", url)
        resp = await client.send(req, stream=True)
    except Exception as exc:  # noqa: BLE001
        await client.aclose()
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, f"Sensor unreachable: {type(exc).__name__}"
        ) from exc
    if resp.status_code != 200:
        await resp.aclose()
        await client.aclose()
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such capture")

    async def passthrough():
        try:
            async for chunk in resp.aiter_bytes():
                yield chunk
        finally:
            await resp.aclose()
            await client.aclose()

    return StreamingResponse(
        passthrough(),
        media_type="application/vnd.tcpdump.pcap",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )
