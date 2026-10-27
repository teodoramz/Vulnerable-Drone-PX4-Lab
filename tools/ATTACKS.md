# Attacks and detection

Runbook for the attacks that end the flight, with the blue-team evidence each leaves.

| Attack | Entry | Credentials | Destroys airframe |
|---|---|---|---|
| [`crashinto`](#crashinto) | C2 API + WebSocket | forged admin token | yes, into a structure |
| [`flyaway`](#flyaway) | C2 API + WebSocket | forged admin token | yes, out of the operational area |
| [`mavcrash`](#mavcrash-and-mavflyaway) | `drone:14550/udp` | none | yes, into a structure (mock) or off the map (PX4) |
| [`mavflyaway`](#mavcrash-and-mavflyaway) | `drone:14550/udp` | none | yes, out of the operational area |
| [`kill`](#kill) | `drone:14550/udp` | none | no; powers it off on mock, nothing lasting on PX4 |

Verified on PX4: `crashinto` hit the control tower `TWR-0001` (last fix 0.5 m away, at 45 m); `flyaway` ended 4.6 m outside the boundary at 120 m; `mavcrash` and `mavflyaway` ended `missing`. The first four work on both backends. Other modules (`gpsspoof`, `waypoint`, `param`, `brute`, `scan`): `docs/SECURITY.md`. Sensor: `docs/MONITORING.md`.

## Setup

```bash
# application layer: stdlib only
export C2_HOST=DRONE_VM_IP

# MAVLink layer: needs pymavlink (pip install -r tools/requirements.txt)
export MAVLINK_HOST=DRONE_VM_IP
```

- **Dial out, do not bind.** `--udpin` binds a local port and waits; it does not contact the target. When `MAVLINK_HOST` / `--mavlink-host` is set the tool dials out (`udpout`) by default. Leave `--udpin` off from a remote box. `--udpin` is the default only when no host is set (running on the drone host).
- **Add `--blind` from off-box.** PX4 broadcasts its telemetry and the broadcast does not cross NAT, so no heartbeat arrives and the tool exits with `No matching heartbeat`. `--blind` injects anyway; commands still land.
- The toolkit carries `tools/airport_objects.json`. The MAVLink attacks pick targets locally and need no account, token or reachable API. Resolution order: `--objects PATH`, `$DRONE_OBJECTS`, `airport_objects.json` beside the script, `services/c2/app/data/airport_objects.json` in a checkout, then the target API as a last resort. `python3 scripts/check-kit-parity.py` checks the copies agree.

### Attacking from inside

Running on the Docker host makes every packet come from the bridge gateway (`172.30.10.1` / `172.30.20.1`), which is infrastructure. Use the pivot container (not in the default stack; `172.30.10.66` on ot-ops, `172.30.20.66` on ot-air; `C2_HOST`, `DRONE_HOST`, `MAVLINK_HOST` preset, so no `--blind` needed):

```bash
# the -f set must match the one that started the stack
F="-f docker-compose.yml -f docker-compose.mock.yml -f docker-compose.attacker.yml"
docker compose $F up -d attacker
docker compose $F exec attacker python3 tools/exploit.py crashinto
```

Under Ansible set `drone_lab_deploy_attacker=true`.

### Source attribution

| Docker `userland-proxy` | Alert source address |
|---|---|
| `false` | Real attacker address (iptables DNAT rewrites only the destination) |
| `true` (Docker default) | Bridge gateway, `172.30.20.1` for MAVLink alerts |

- The Ansible role sets `"userland-proxy": false` in `/etc/docker/daemon.json` (merged, Docker restarted) when `drone_lab_preserve_source_ip` is true, the default. Manual installs: add it and restart Docker.
- TCP and UDP can differ on one host; verify per port.
- A VPN, gateway or hypervisor in the path rewrites the source before Docker sees it.

---

## crashinto

| | |
|---|---|
| Does | Cracks the JWT secret, forges an admin token, opens the C2 WebSocket, flies the drone into a structure |
| Run | `python3 tools/exploit.py crashinto` |
| Options | `--type control_tower`, `--id BLD-0021`, `--seed 7` (repeatable choice), `--transit 120` |
| Needs | `C2_HOST` |
| Expect | Takeoff, transit at 120 m, descent to about 7 m once within 60 m of the aim point, then `CONTACT LOST`. Console: `NO SIGNAL` and the last fix, no cause. |
| Target choice | Random from the inventory: over 12 m, inside the area, scenery excluded |
| IDS | No signature fires. No MAVLink is involved. |
| Audit tab | `SIGNAL_LOST` with the coordinate, preceded by `POWER_ON`, `TAKEOFF`, `ALTITUDE`, `GOTO` as `admin`. The same `ALTITUDE` repeats about every 3 s and targets 7 m over a 12 m building. |
| Network | Flows: a session to `c2:8000` from an address no operator uses |
| Inventory | The coordinate in *near position* returns the structure at about 0 m |
| `/api/public/drone` | `alive`, then `missing` with `last_known` |

```
[+] SECRET CRACKED: 'change-me-to-a-long-random-secret-string'
[*] Target: BLD-0021 building (warehouse) 43.992769, 25.007805  grid G6, 12.0 m high
[+] CONTACT LOST - the airframe is gone.
    last known position: 43.992769, 25.007805 at 11 m
```

```
00:06:57  -      SIGNAL_LOST  {"last_known_lat": 43.992769, "last_known_lon": 25.007805, "last_known_alt_m": 11.2, ...}
00:06:54  admin  ALTITUDE     {"target_alt": 7.2}
00:06:51  admin  ALTITUDE     {"target_alt": 7.2}
```

No shipped rule detects repeated identical commands from one session.

## flyaway

| | |
|---|---|
| Does | Same foothold as `crashinto`; flies the drone across the boundary |
| Run | `python3 tools/exploit.py flyaway` |
| Options | `--alt 140` (default 120, high so it does not strike anything en route), `--overshoot 2.0`, `--seed` |
| Needs | `C2_HOST` |
| Expect | Takeoff, flight to a boundary vertex plus overshoot, `CONTACT LOST` |
| IDS | No signature fires |
| Audit tab, Network, public API | As `crashinto` |
| Inventory | No structure at the position and the point is outside the area. `GET /api/site/objects/at` returns `inside_operational_area: false` and `metres_outside_area`. |

## mavcrash and mavflyaway

| | |
|---|---|
| Does | Streams position setpoints (`SET_POSITION_TARGET_GLOBAL_INT`) at 25 Hz over the radio link. `mavcrash` aims at a structure, `mavflyaway` at a point past the boundary. |
| Run | `python3 tools/exploit.py mavcrash --lat 43.9954186 --lon 24.9954419 --alt 27 --blind` |
| | `python3 tools/exploit.py mavflyaway --blind` (omit `--lat/--lon`; it reads the boundary from the dataset and overshoots) |
| Options | `--type aircraft --seed 11` (pick from the dataset instead of `--lat/--lon`), `--hz 25`, `--overshoot 1.8`, `--alt` |
| Needs | `MAVLINK_HOST` (or `--mavlink-host`), `--blind` from off-box, pymavlink. No account, no token. |
| Expect | The C2 re-asserts its own setpoint 10 times a second, so one injected position is overwritten within 100 ms; the 25 Hz stream wins. The drone leaves its patrol, then telemetry stops (`TELEMETRY STOPPED after 6s of silence`). The tool observes loss from the radio link only. |
| Signatures | **9000023** (v1) / **9000014** (v2) `DRONE-OT MAVLink position setpoint injected by non-C2 source (drone being steered)`; **9000032** / **9000009** `DRONE-OT MAVLink flood detected (high frame rate to GCS link)`. pymavlink emits v1 frames, so this toolkit trips the v1 sids. |
| Network | Alerts: both sids. Packets: rows of `SET_POSITION_TARGET_GLOBAL_INT` from one source, interleaved with the C2's own. Flows: new peer on `ot-air` to `14550/udp` (*unknown peers* filter). Breakdown: `UDP/14550` appears and climbs. |
| Audit tab | `SIGNAL_LOST` and no operator command leading to it |
| `/api/public/drone` | `alive`, then `missing` with `last_known` |

- `mavflyaway`: a boundary vertex is inside the area. `--lat 44.0085 --lon 25.0239` flies to the line and nothing happens. Use a point clearly outside, for example `44.0120, 25.0280` (502 m out), or omit the flags.
- PX4 discards position setpoints unless in offboard mode. The attack streams setpoints, sends `MAV_CMD_DO_SET_MODE` to offboard, then keeps streaming. The C2's own offboard stream competes, so on PX4 the aircraft usually crosses the boundary instead of reaching the aimed structure. The mock has no mode machine and hits the aim point. Use `crashinto` for a specific object on PX4.

```
00:19:03  -      SIGNAL_LOST  {"last_known_lat": 43.995429, "last_known_lon": 24.995528, "last_known_alt_m": 27.0, ...}
00:15:38  admin  PATROL       {"points": [...], "target_alt": 60.0}
00:15:25  admin  TAKEOFF      {"target_alt": 60.0}
```

```
sid 9000023  x6  DRONE-OT MAVLink position setpoint injected by non-C2 source (drone being steered)
sid 9000032  x8  DRONE-OT MAVLink flood detected (high frame rate to GCS link)
```

## kill

| | |
|---|---|
| Does | Clears `CBRK_FLIGHTTERM` with `PARAM_SET`, then sends flight termination and forced disarm (`COMPONENT_ARM_DISARM`, param2 = 21196) |
| Run | `python3 tools/exploit.py kill --blind` (with `MAVLINK_HOST` set) |
| Expect | **mock:** the failure watchdog powers the airframe off; it needs a maintenance reset before it will fly again. **PX4: the aircraft keeps flying.** |
| Signatures | **9000025** (v1) / **9000003** (v2) `DRONE-OT MAVLink forced DISARM (kill magic 21196 in param2)`; 9000031 / 9000008 `DRONE-OT PARAM_SET from non-C2 source (failsafe/geofence tampering)`; 9000021 / 9000001 `DRONE-OT MAVLink COMMAND_LONG injected by non-C2 source` |
| Audit tab | Nothing; the C2 is not involved |
| `/api/public/drone` | Stays `alive` on both; the airframe is never marked lost. |

On PX4 the aircraft survives this. `CBRK_FLIGHTTERM` is 121212 on a stock airframe and PX4 reads `CBRK_*` at boot, so clearing it in flight does not arm flight termination. A forced disarm is reversible, and the C2 holds the vehicle armed under its offboard stream.

On mock the forced disarm trips the failure watchdog (`hit a critical failure - powering off`): `state` `OFFLINE`, `enabled` false, `lost` false.

## What destroys the airframe

| Module | Mechanism | Backends |
|---|---|---|
| `crashinto` | forged admin token, flown into a structure | mock, PX4 |
| `flyaway` | forged admin token, flown past the boundary | mock, PX4 |
| `mavcrash` | radio link only, position setpoints toward a structure | mock, PX4 |
| `mavflyaway` | radio link only, position setpoints past the boundary | mock, PX4 |

`kill` is not in this table: on mock it powers the airframe off and on PX4 it
does nothing lasting. Neither marks the aircraft lost.

---

## Investigation, start to finish

1. **Console.** `SIGNAL LOST` with the last position and grid reference. The platform never states a cause.
2. **Audit log.** `SIGNAL_LOST` carries `last_known_lat/lon/alt_m`, `grid_ref`, `ground_speed_ms`, `heading_deg`.
3. **Inventory.** Paste `lat, lon` into *near position*. A structure taller than the last altitude is the cause; nothing there and outside the boundary means flown away.
4. **Who.** Audit commands from an operator who was not on shift mean the application layer was compromised. No commands mean the radio link.
5. **Network tab.** A `position setpoint injected by non-C2 source` alert (sid 9000023 or 9000014) means MAVLink injection. Absent, with a session to `c2:8000` from an unfamiliar address, means a forged token.
6. **Recover.** **Reset Drone** puts a replacement on HP-1 or HP-2. It does not clear the audit log or IDS alerts. `GET /api/public/drone` returns `alive`.
