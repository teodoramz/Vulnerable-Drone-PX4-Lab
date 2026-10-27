from __future__ import annotations

import contextlib
import os
import shutil
import signal
import subprocess

PX4_ROOT = "PX4-Autopilot"
INSTANCE_DIR = f"{PX4_ROOT}/build/px4_sitl_default/instance_{{i}}"


class Px4Agent:
    """Lifecycle manager for PX4 SITL instances: process spawn/kill and instance-dir wiping.
    No flight logic; the C2 flies the instances over MAVLink."""

    def __init__(self, drones: list[dict], c2_host: str = "c2", base_port: int = 14540):
        self.c2_host = c2_host
        self.base_port = base_port
        self.drones: dict[int, dict] = {
            d["id"]: {**d, "enabled": False, "proc": None} for d in drones
        }

    def list_drones(self) -> list[dict]:
        return [
            {
                "id": d["id"],
                "callsign": d["callsign"],
                "enabled": d["enabled"],
                "lat": 0.0,
                "lon": 0.0,
                "rel_alt": 0.0,
                "armed": False,
                "home_lat": d["home_lat"],
                "home_lon": d["home_lon"],
            }
            for d in sorted(self.drones.values(), key=lambda x: x["id"])
        ]

    async def relocate(self, drone_id: int, lat: float, lon: float,
                       alt: float | None = None) -> bool:
        """Record a new home for the next spawn.

        The C2 re-anchors PX4's local NED frame onto its own home, so this only
        keeps the registry consistent.
        """
        drone = self.drones.get(drone_id)
        if drone is None:
            return False
        drone["home_lat"] = lat
        drone["home_lon"] = lon
        if alt is not None:
            drone["home_alt"] = alt
        return True

    async def power(self, drone_id: int, on: bool) -> bool:
        drone = self.drones.get(drone_id)
        if drone is None:
            return False
        if on and not drone["enabled"]:
            self._spawn(drone_id)
        elif not on and drone["enabled"]:
            self._kill(drone_id)
        return True

    def _spawn(self, drone_id: int) -> None:
        drone = self.drones[drone_id]
        instance = INSTANCE_DIR.format(i=drone_id)
        if os.path.exists(instance):
            shutil.rmtree(instance, ignore_errors=True)

        # SIH airframe 10040; PX4 opens onboard MAVLink on remote port 14540 + i.
        env = {
            **os.environ,
            "PX4_SYS_AUTOSTART": "10040",
            "PX4_SIMULATOR": "sihsim",
            "PX4_SIM_MODEL": "quadx",
        }
        print(f"[px4-agent] spawning PX4 instance {drone_id}", flush=True)
        # Own process group so _kill can take down the whole tree.
        drone["proc"] = subprocess.Popen(
            ["./build/px4_sitl_default/bin/px4", "-i", str(drone_id)],
            cwd=PX4_ROOT,
            env=env,
            start_new_session=True,
        )
        drone["enabled"] = True

    def _kill(self, drone_id: int) -> None:
        drone = self.drones[drone_id]
        proc = drone.get("proc")
        if proc is not None:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError, OSError):
                try:
                    proc.kill()
                except Exception:  # noqa: BLE001
                    pass
            with contextlib.suppress(Exception):
                proc.wait(timeout=5)
        drone["proc"] = None
        drone["enabled"] = False
        instance = INSTANCE_DIR.format(i=drone_id)
        if os.path.exists(instance):
            shutil.rmtree(instance, ignore_errors=True)
