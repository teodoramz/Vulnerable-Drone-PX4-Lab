#!/usr/bin/env python3
"""Check that the sensor's alert payload is accepted by the C2.

Compares the two Pydantic models and round-trips a sample alert, so schema drift
fails here instead of silently breaking alerting.

    python3 scripts/check-ids-contract.py

Run from the repo root in an env that can import both packages (e.g. .venv-sensor).
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load(name: str, path: Path):
    """Load a module by path; both services root their package at `app`, so plain imports clash."""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


SensorAlert = load(
    "sensor_models", ROOT / "services" / "sensor" / "app" / "models.py"
).Alert
C2AlertIn = load(
    "c2_ids_schema", ROOT / "services" / "c2" / "app" / "schemas" / "ids.py"
).IdsAlertIn

failures: list[str] = []

sensor_fields = SensorAlert.model_fields
c2_fields = C2AlertIn.model_fields

# 1. Every field the sensor sends must exist on the C2 side.
for name in sensor_fields:
    if name not in c2_fields:
        failures.append(f"sensor sends '{name}' but the C2 schema has no such field")

# 2. Every field the C2 *requires* must be one the sensor always provides.
for name, field in c2_fields.items():
    if field.is_required():
        if name not in sensor_fields:
            failures.append(f"C2 requires '{name}' but the sensor never sends it")
        elif not sensor_fields[name].is_required():
            failures.append(
                f"C2 requires '{name}' but the sensor treats it as optional "
                f"-- a port-less or ICMP alert would be rejected"
            )

# 3. A realistic alert, including the port-less shape Suricata emits for
#    ICMP and several protocol events, must survive the round trip.
samples = [
    {
        "ts": "2026-09-21T04:30:00.000000+0000",
        "signature": "DRONE-OT MAVLink COMMAND_LONG injected by non-C2 source",
        "sid": 9000001,
        "severity": 1,
        "category": "Attempted Administrator Privilege Gain",
        "src_ip": "10.10.30.66",
        "src_port": 54211,
        "dest_ip": "10.10.40.20",
        "dest_port": 14550,
        "proto": "UDP",
        "iface": "ot-air",
    },
    {
        "ts": "2026-09-21T04:31:00.000000+0000",
        "signature": "SURICATA ICMPv4 unknown type",
        "sid": 2200024,
        "severity": 3,
        "src_ip": "10.10.30.66",
        "dest_ip": "10.10.20.10",
        "proto": "ICMP",
    },
]

for i, raw in enumerate(samples):
    try:
        produced = SensorAlert(**raw).model_dump()
    except Exception as exc:  # noqa: BLE001
        failures.append(f"sample {i}: sensor could not build the alert: {exc}")
        continue
    try:
        C2AlertIn(**produced)
    except Exception as exc:  # noqa: BLE001
        failures.append(f"sample {i}: C2 rejected the sensor's payload: {exc}")

if failures:
    print("IDS CONTRACT BROKEN:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)

print(f"IDS contract OK - {len(sensor_fields)} sensor fields accepted by the C2, "
      f"{len(samples)} sample alerts round-tripped (including a port-less one)")
