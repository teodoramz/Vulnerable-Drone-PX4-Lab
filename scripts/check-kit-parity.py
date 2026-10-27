#!/usr/bin/env python3
"""Check that the attack kit's copies still agree with the originals.

tools/airport_objects.json is a trimmed copy of the C2's dataset (services/c2/app/data/); it may
carry fewer fields but not different values, because exploit.py prefers it when aiming.
Also checks these byte-identical duplicates:

    tools/mavlink_attacks.sh == scripts/mavlink_attacks.sh
    tools/airport_map.jpg    == services/frontend/public/map/airport.jpg

Run from the repo root:  python3 scripts/check-kit-parity.py
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
CANONICAL = REPO / "services" / "c2" / "app" / "data" / "airport_objects.json"
KIT = REPO / "tools" / "airport_objects.json"

# (copy, original) pairs that must stay byte-identical.
DUPLICATES = (
    ("tools/mavlink_attacks.sh", "scripts/mavlink_attacks.sh"),
    ("tools/airport_map.jpg", "services/frontend/public/map/airport.jpg"),
)

# Rounding places before comparing: 7 decimals of latitude is ~1 cm.
COORD_PLACES = 7
HEIGHT_PLACES = 3


def fail(msg: str) -> None:
    print(f"FAIL  {msg}")
    sys.exit(1)


def main() -> None:
    for path in (CANONICAL, KIT):
        if not path.is_file():
            fail(f"missing dataset: {path.relative_to(REPO)}")

    canon = json.loads(CANONICAL.read_text())
    kit = json.loads(KIT.read_text())

    c_objs = {o["id"]: o for o in canon["objects"]}
    k_objs = {o["id"]: o for o in kit["objects"]}

    if set(c_objs) != set(k_objs):
        only_c = sorted(set(c_objs) - set(k_objs))[:5]
        only_k = sorted(set(k_objs) - set(c_objs))[:5]
        fail(
            f"object sets differ: {len(c_objs)} canonical vs {len(k_objs)} in the kit"
            + (f"; missing from the kit e.g. {only_c}" if only_c else "")
            + (f"; unknown to the C2 e.g. {only_k}" if only_k else "")
        )

    mismatches: list[str] = []
    for oid, c in c_objs.items():
        k = k_objs[oid]
        if c.get("type") != k.get("type"):
            mismatches.append(f"{oid}: type {c.get('type')} vs {k.get('type')}")
        for field, places in (("lat", COORD_PLACES), ("lon", COORD_PLACES),
                              ("height_m", HEIGHT_PLACES)):
            cv, kv = c.get(field), k.get(field)
            if cv is None and kv is None:
                continue
            if cv is None or kv is None or round(cv, places) != round(kv, places):
                mismatches.append(f"{oid}: {field} {cv} vs {kv}")

    if mismatches:
        for m in mismatches[:10]:
            print(f"  {m}")
        extra = len(mismatches) - 10
        fail(f"{len(mismatches)} field(s) disagree"
             + (f" ({extra} more not shown)" if extra > 0 else ""))

    # The boundary separates collision from fly-away; it must match exactly.
    c_ring = canon["operational_area"]["boundary_latlon"]
    k_ring = (kit.get("operational_area") or {}).get("boundary_latlon")
    if k_ring is None:
        fail("the kit's dataset has no operational_area.boundary_latlon")
    if len(c_ring) != len(k_ring):
        fail(f"boundary has {len(c_ring)} vertices canonically, {len(k_ring)} in the kit")
    for i, (cv, kv) in enumerate(zip(c_ring, k_ring)):
        if [round(v, COORD_PLACES) for v in cv] != [round(v, COORD_PLACES) for v in kv]:
            fail(f"boundary vertex {i} differs: {cv} vs {kv}")

    print(
        f"OK    {len(c_objs)} objects and a {len(c_ring)}-vertex boundary agree "
        f"between {CANONICAL.relative_to(REPO)} and {KIT.relative_to(REPO)}"
    )

    # Plain byte comparison.
    for copy, original in DUPLICATES:
        cp, op = REPO / copy, REPO / original
        if not cp.is_file():
            fail(f"missing: {copy}")
        if not op.is_file():
            fail(f"missing: {original}")
        if hashlib.sha256(cp.read_bytes()).digest() != hashlib.sha256(op.read_bytes()).digest():
            fail(f"{copy} and {original} have diverged -- copy whichever is "
                 f"correct over the other")
        print(f"OK    {copy} matches {original}")


if __name__ == "__main__":
    main()
