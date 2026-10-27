from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import AsyncIterator

logger = logging.getLogger("sensor.tailer")


async def follow(path: str, poll_interval: float = 0.5, stop_event: asyncio.Event | None = None) -> AsyncIterator[str]:
    """`tail -F`-style async generator yielding complete lines appended to `path`.

    - Waits for the file to appear.
    - Skips history only for a file that existed at start; a file that appears
      later is read from the beginning.
    - Reopens on truncation or inode change.
    - Logs and keeps polling on read errors; stops only on `stop_event`.
    """
    fh = None
    inode = None
    pos = 0
    existed_at_start = os.path.exists(path)
    first_open = True

    try:
        while stop_event is None or not stop_event.is_set():
            if fh is None:
                if not os.path.exists(path):
                    await asyncio.sleep(poll_interval)
                    continue
                try:
                    fh = open(path, "r", encoding="utf-8", errors="replace")  # noqa: SIM115
                    inode = os.fstat(fh.fileno()).st_ino
                    if first_open and existed_at_start:
                        fh.seek(0, os.SEEK_END)  # pre-existing file: skip history
                    else:
                        fh.seek(0)  # newly appeared or rotated: read it all
                    pos = fh.tell()
                    first_open = False
                    logger.info("tailer: opened %s at offset %d", path, pos)
                except OSError as exc:
                    logger.warning("tailer: failed to open %s: %s", path, exc)
                    await asyncio.sleep(poll_interval)
                    continue

            try:
                current_inode = os.stat(path).st_ino
            except OSError:
                current_inode = None

            if current_inode is None:
                # File disappeared (rotation mid-write) - close and retry open.
                fh.close()
                fh = None
                await asyncio.sleep(poll_interval)
                continue

            if current_inode != inode:
                logger.info("tailer: %s rotated, reopening from start", path)
                fh.close()
                fh = None
                continue

            try:
                size = os.fstat(fh.fileno()).st_size
            except OSError:
                size = pos
            if size < pos:
                # Truncated in place - rewind.
                logger.info("tailer: %s truncated, rewinding", path)
                fh.seek(0)
                pos = 0

            line = fh.readline()
            if line:
                if line.endswith("\n"):
                    pos = fh.tell()
                    yield line
                else:
                    # Partial line (Suricata mid-write) - back off and retry
                    # from the same spot rather than yielding a half record.
                    fh.seek(pos)
                    await asyncio.sleep(poll_interval)
            else:
                await asyncio.sleep(poll_interval)
    finally:
        if fh is not None:
            fh.close()
