from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

from app.config import settings
from app.state import SensorState

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

state = SensorState(settings)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await state.start()
    try:
        yield
    finally:
        await state.stop()


app = FastAPI(title="Drone-Lab Sensor", version="1.0.0", lifespan=lifespan)


def _parse_since(since: str | None) -> datetime | None:
    if not since:
        return None
    try:
        # Suricata emits "+0000" offsets; fromisoformat() needs "+00:00" or "Z".
        s = since.strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        elif len(s) >= 5 and (s[-5] in "+-") and s[-3] != ":":
            s = f"{s[:-2]}:{s[-2:]}"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _ts(record_ts: str) -> datetime | None:
    return _parse_since(record_ts)


@app.get("/health")
async def health() -> dict:
    eve_exists = os.path.exists(settings.eve_path)
    return {
        "status": "ok",
        "eve_path": settings.eve_path,
        "eve_path_exists": eve_exists,
        "ifaces": settings.iface_list,
        "buffered_alerts": len(state.alerts),
        "buffered_flows": len(state.flows),
        "last_event_ts": state.last_event_ts,
        "ws_clients": state.hub.count,
    }


@app.get("/alerts")
async def get_alerts(
    limit: int = Query(default=100, le=2000),
    severity: int | None = Query(default=None, ge=1, le=3),
    since: str | None = Query(default=None),
) -> list[dict]:
    since_dt = _parse_since(since) if since else None

    def predicate(alert) -> bool:
        if severity is not None and alert.severity != severity:
            return False
        if since_dt is not None:
            alert_dt = _ts(alert.ts)
            if alert_dt is None or alert_dt <= since_dt:
                return False
        return True

    need_filter = severity is not None or since_dt is not None
    items = state.alerts.recent(limit, predicate if need_filter else None)
    return [a.model_dump() for a in items]


@app.get("/flows")
async def get_flows(limit: int = Query(default=100, le=2000)) -> list[dict]:
    items = state.flows.recent(limit)
    return [f.model_dump() for f in items]


@app.get("/live")
async def get_live(limit: int = Query(default=200, le=2000)) -> dict:
    """Per-flow packet and byte counters over a rolling window (flows still open)."""
    return state.live.snapshot(limit)


@app.get("/packets")
async def get_packets(
    limit: int = Query(default=200, le=1000),
    mavlink_only: bool = Query(default=False),
) -> dict:
    """Recent packets, with the decoded MAVLink message where there is one."""
    return state.live.recent_packets(limit=limit, mavlink_only=mavlink_only)


@app.get("/breakdown")
async def get_breakdown() -> dict:
    """Traffic totals by protocol and service port, plus MAVLink message mix."""
    return state.live.breakdown()


@app.get("/captures")
async def list_captures() -> dict:
    """List the rotating packet captures on disk (metadata only)."""
    directory = "/var/log/suricata/captures"
    try:
        entries = []
        # Suricata appends .<unix-ts>, so match on the prefix.
        for name in sorted(os.listdir(directory)):
            if not name.startswith("ot-lab.pcap"):
                continue
            path = os.path.join(directory, name)
            st = os.stat(path)
            entries.append({
                "name": name,
                "bytes": st.st_size,
                "modified": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
            })
        return {"available": True, "dir": directory, "captures": entries}
    except OSError as exc:
        return {"available": False, "dir": directory, "captures": [], "error": str(exc)}


@app.get("/captures/{name}")
async def download_capture(name: str):
    """Download one capture file."""
    directory = "/var/log/suricata/captures"
    # Reject path traversal before joining the name.
    if "/" in name or "\\" in name or not name.startswith("ot-lab.pcap"):
        raise HTTPException(status_code=404, detail="No such capture")
    path = os.path.join(directory, name)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="No such capture")
    return FileResponse(path, media_type="application/vnd.tcpdump.pcap", filename=name)


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    state.hub.connect(ws)
    try:
        # Replay buffered history so the client populates immediately.
        for alert in state.alerts.all():
            await ws.send_text(json.dumps({"type": "alert", "data": alert.model_dump()}))
        for flow in state.flows.all():
            await ws.send_text(json.dumps({"type": "flow", "data": flow.model_dump()}))

        while True:
            # Push-only stream; receiving detects client disconnects.
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        state.hub.disconnect(ws)
