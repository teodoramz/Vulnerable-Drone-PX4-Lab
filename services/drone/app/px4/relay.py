"""Bidirectional UDP relay between PX4 instance i (127.0.0.1:14540+i) and the C2.

Uses unconnected sockets and swallows transient errors so a C2 that is not
listening yet cannot kill it with ECONNREFUSED.

Usage:  python relay.py <local_port> <remote_host> <remote_port>
"""
from __future__ import annotations

import socket
import sys
import threading
import time


def _resolve(host: str) -> str:
    while True:
        try:
            return socket.gethostbyname(host)
        except OSError:
            time.sleep(1)


def main() -> None:
    local_port = int(sys.argv[1])
    remote_host = sys.argv[2]
    remote_port = int(sys.argv[3])
    remote_addr = (_resolve(remote_host), remote_port)

    # PX4 side.
    local = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    local.bind(("127.0.0.1", local_port))

    # C2 side.
    remote = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    remote.bind(("0.0.0.0", 0))

    state: dict[str, tuple | None] = {"px4_addr": None}

    def px4_to_c2() -> None:
        while True:
            try:
                data, addr = local.recvfrom(65535)
                state["px4_addr"] = addr
                remote.sendto(data, remote_addr)
            except OSError:
                pass

    def c2_to_px4() -> None:
        while True:
            try:
                data, _ = remote.recvfrom(65535)
                if state["px4_addr"] is not None:
                    local.sendto(data, state["px4_addr"])
            except OSError:
                pass

    threading.Thread(target=px4_to_c2, daemon=True).start()
    c2_to_px4()


if __name__ == "__main__":
    main()
