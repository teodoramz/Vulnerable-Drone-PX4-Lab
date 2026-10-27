# Simulation backends

Both backends put real MAVLink 2 on the wire. They differ in the autopilot behind it.

| | `px4` (default) | `mock` |
|---|---|---|
| Autopilot | Real PX4 firmware (SIH) | Python kinematics |
| EKF, failsafes, parameters | Real | Absent / stubbed |
| First boot | 20-40 min firmware build (cached in volume `px4build`) | about 2 min |
| Requires | Linux or WSL2, privileged container, 1 GB shm | Any OS |
| Use for | The scenario | Development, CI, demos |

Select with `DRONE_BACKEND`, or add `-f docker-compose.mock.yml`.

## PX4 backend

- SIH (Simulation-In-Hardware) is PX4's in-process quadcopter model with simulated GPS, barometer and magnetometer. No Gazebo server runs; the image ships Gazebo libraries only because the `px4` binary links against them. Instances are independent, so `DRONE_COUNT` above 1 works.
- Spawn command: `PX4_SYS_AUTOSTART=10040 PX4_SIMULATOR=sihsim PX4_SIM_MODEL=quadx ./build/px4_sitl_default/bin/px4 -i 0` (`10040` is `sihsim_quadx`).
- `_spawn` starts `px4` in its own process group and `_kill` uses `os.killpg`, so power cycles do not orphan a process that holds the MAVLink port. `init: true` (tini) reaps zombies.
- The C2 waits for MAVSDK `health_all_ok()` before declaring `READY`, and `arm()` retries on transient rejection.
- Positioning: SIH's GPS origin is not deterministic. The C2 reads local NED position and re-anchors it on the chosen pad (`lat = home_lat + north_m / 111320`, `lon = home_lon + east_m / (111320 * cos(home_lat))`). `goto_location()` converts back to NED and flies with offboard `set_position_ned`. All of this is inside `MavsdkLink`.
- The entrypoint writes `HOME_LAT`, `HOME_LON`, `HOME_ALT` into the airframe as `SIH_LOC_LAT0/LON0/H0` (no recompile) and patches a MAVLink instance onto the radio port `14550` (stock PX4 SITL does not bind it).
- The pad comes from the site dataset (HP-1 or HP-2): the C2 sets the runtime home on power-on and informs the drone service (`Px4Agent.relocate()`). The env vars remain the initial value and the vertical datum.

## Mock backend

- `app/mock/simulator.py` integrates the same low-level verbs PX4 exposes; `app/mavlink/transport.py` fronts it with a MAVLink 2 UDP surface (pymavlink).
- Emits `HEARTBEAT` (1 Hz), `GLOBAL_POSITION_INT` (10 Hz), `GPS_RAW_INT`, `SYS_STATUS`, `ATTITUDE`, `EXTENDED_SYS_STATE`.
- Consumes `COMMAND_LONG` (arm/disarm including the 21196 force magic, takeoff, land, RTL, reposition), `SET_MODE`, `SET_POSITION_TARGET_GLOBAL_INT`, `MISSION_COUNT` / `MISSION_ITEM_INT`, `GPS_INPUT`, `PARAM_SET`; replies with `COMMAND_ACK`.
- MAVLink and WebSocket control mutate the same simulator state.

Limits of the mock:

- No EKF: GPS spoofing moves the reported position directly.
- No failsafe logic: geofence, RC-loss and battery failsafes do not exist.
- Stub parameters: `PARAM_SET` is stored and changes nothing.
- The C2's own commands use the WebSocket verb protocol, not MAVLink, so any MAVLink command trips the "non-C2 source" rules.

## Behaviour under attack

| Attack | mock | PX4 |
|---|---|---|
| `crashinto`, `flyaway` | destroys the airframe | destroys the airframe |
| `mavcrash`, `mavflyaway` | destroys the airframe; hits the aim point | destroys the airframe; aim point contested |
| `kill` | powered off by the failure watchdog; not marked lost | no effect: `CBRK_FLIGHTTERM` is read at boot and the C2 re-arms |
| `mode`, `rtl`, `arm`, `disarm` | works | works |
| `param`, `waypoint` | accepted; no behavioural effect for `param` | act on real parameter and mission state |
| Telemetry reaching an off-host attacker | yes | no |

- Real PX4 discards position setpoints unless in offboard mode. The attack streams, switches to offboard with `MAV_CMD_DO_SET_MODE`, and keeps streaming. The C2's competing offboard stream pulls the aircraft toward the boundary instead of the aim point. Commands are not mode-gated.
- PX4 does not stream telemetry to a peer that dialled in, and its broadcast does not cross NAT. Off-host MAVLink modules need `--blind`. From the pivot container the broadcast is in range.

Details: `docs/ATTACKS.md`.

## Ports

| Port | Direction | Purpose |
|---|---|---|
| `14540/udp` | drone to c2 | Offboard MAVLink, the C2's control link (MAVSDK) |
| `14550/udp` | drone, broadcast | GCS radio link, unauthenticated, the toolkit's target |
| `9100/tcp` | c2 to drone | Lifecycle agent, unauthenticated |
| `8888/udp` | px4 to agent | Micro-XRCE-DDS, unused by the C2 |
