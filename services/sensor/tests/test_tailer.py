import asyncio

import pytest

from app.tailer import follow


@pytest.mark.asyncio
async def test_follow_yields_appended_lines_and_skips_history(tmp_path):
    path = tmp_path / "eve.json"
    path.write_text('{"already": "here"}\n')  # written before follow() starts

    stop = asyncio.Event()
    gen = follow(str(path), poll_interval=0.02, stop_event=stop)

    async def append_after_delay():
        await asyncio.sleep(0.05)
        with open(path, "a") as f:
            f.write('{"new": 1}\n')
            f.write('{"new": 2}\n')

    asyncio.create_task(append_after_delay())

    lines = []

    async def collect():
        async for line in gen:
            lines.append(line.strip())
            if len(lines) == 2:
                stop.set()
                break

    await asyncio.wait_for(collect(), timeout=2)

    assert lines == ['{"new": 1}', '{"new": 2}']  # history line was NOT replayed


@pytest.mark.asyncio
async def test_follow_waits_for_file_to_appear(tmp_path):
    path = tmp_path / "not-yet.json"
    stop = asyncio.Event()
    gen = follow(str(path), poll_interval=0.02, stop_event=stop)

    async def create_after_delay():
        await asyncio.sleep(0.08)
        path.write_text('{"hello": true}\n')

    asyncio.create_task(create_after_delay())

    got = None

    async def collect():
        nonlocal got
        async for line in gen:
            got = line.strip()
            stop.set()
            break

    await asyncio.wait_for(collect(), timeout=2)
    assert got == '{"hello": true}'


@pytest.mark.asyncio
async def test_follow_handles_truncation_mid_stream(tmp_path):
    """A long-lived `follow()` must rewind when the file is truncated in place."""
    path = tmp_path / "eve.json"
    path.write_text("")  # exists at start, so history-skipping applies

    stop = asyncio.Event()
    gen = follow(str(path), poll_interval=0.02, stop_event=stop)
    lines = []

    # Append after follow() starts, or the lines would be skipped as history.
    async def append_after_delay():
        await asyncio.sleep(0.05)
        with open(path, "a") as f:
            f.write('{"a": 1}\n{"b": 2}\n{"c": 3}\n')

    asyncio.create_task(append_after_delay())

    async def drain_first_three():
        async for line in gen:
            lines.append(line.strip())
            if len(lines) == 3:
                return

    await asyncio.wait_for(drain_first_three(), timeout=2)
    assert lines == ['{"a": 1}', '{"b": 2}', '{"c": 3}']

    # Truncate to something shorter than the current read offset, then
    # append a new line - the tailer must detect size < pos and rewind.
    with open(path, "w") as f:
        f.write('{"d": 4}\n')

    async def get_next():
        async for line in gen:
            return line.strip()

    got = await asyncio.wait_for(get_next(), timeout=2)
    stop.set()
    assert got == '{"d": 4}'
