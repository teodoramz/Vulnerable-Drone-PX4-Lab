from __future__ import annotations

import asyncio
import contextlib
import logging

from app.config import Settings
from app.eve import parse_eve_line
from app.hub import WebSocketHub
from app.livetap import LiveTap
from app.models import Alert, Flow
from app.pusher import AlertPusher
from app.ring_buffer import RingBuffer
from app.tailer import follow

logger = logging.getLogger("sensor.state")


class SensorState:
    """Owns the ring buffers, WS hub and C2 pusher, and wires the eve.json tailer to them."""

    def __init__(self, settings: Settings, pusher: AlertPusher | None = None) -> None:
        self.settings = settings
        self.alerts: RingBuffer[Alert] = RingBuffer(settings.alert_buffer_size)
        self.flows: RingBuffer[Flow] = RingBuffer(settings.flow_buffer_size)
        self.hub = WebSocketHub()
        # Live per-flow counters; Suricata only logs flows when they end.
        self.live = LiveTap(settings.iface_list)
        self.pusher = pusher or AlertPusher(settings)
        # Bounded; the oldest pending push is dropped when full.
        self.push_queue: asyncio.Queue[Alert] = asyncio.Queue(maxsize=settings.alert_buffer_size)

        self.last_event_ts: str | None = None
        self._tail_task: asyncio.Task | None = None
        self._push_task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    # ── ingestion (testable without real files / background tasks) ─────
    async def process_line(self, line: str) -> Alert | Flow | None:
        default_iface = self.settings.iface_list[0] if self.settings.iface_list else ""
        record = parse_eve_line(line, default_iface=default_iface)
        if record is None:
            return None

        self.last_event_ts = record.ts

        if isinstance(record, Alert):
            self.alerts.append(record)
            await self.hub.broadcast({"type": "alert", "data": record.model_dump()})
            try:
                self.push_queue.put_nowait(record)
            except asyncio.QueueFull:
                # A slow C2 must never back up ingestion.
                logger.warning("push queue full; dropping oldest pending push")
                with contextlib.suppress(asyncio.QueueEmpty, asyncio.QueueFull):
                    self.push_queue.get_nowait()
                    self.push_queue.put_nowait(record)
        elif isinstance(record, Flow):
            self.flows.append(record)
            await self.hub.broadcast({"type": "flow", "data": record.model_dump()})

        return record

    # ── background tasks ────────────────────────────────────────────
    async def _tail_loop(self) -> None:
        try:
            async for line in follow(self.settings.eve_path, self.settings.eve_poll_interval, self._stop_event):
                try:
                    await self.process_line(line)
                except Exception:  # noqa: BLE001 - one bad record must never kill the tailer
                    logger.exception("error processing eve line")
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("tail loop crashed unexpectedly")

    async def _push_loop(self) -> None:
        try:
            while True:
                alert = await self.push_queue.get()
                try:
                    await self.pusher.push(alert)
                except Exception:  # noqa: BLE001 - never let a push failure kill the worker
                    logger.exception("unexpected error pushing alert sid=%s", alert.sid)
                finally:
                    self.push_queue.task_done()
        except asyncio.CancelledError:
            raise

    async def start(self) -> None:
        await self.live.start()
        self._stop_event.clear()
        self._tail_task = asyncio.create_task(self._tail_loop())
        self._push_task = asyncio.create_task(self._push_loop())

    async def stop(self) -> None:
        await self.live.stop()
        self._stop_event.set()
        for task in (self._tail_task, self._push_task):
            if task is not None:
                task.cancel()
        for task in (self._tail_task, self._push_task):
            if task is not None:
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        await self.pusher.aclose()
