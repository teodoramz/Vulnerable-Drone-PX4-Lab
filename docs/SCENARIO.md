# Scenario

Marwick International Airport runs a standing aerial security patrol with one surveillance drone, flown from a ground station outside the protected network. The user is either the operator or an attacker inside the network.

## Site

The map is a picture (`/map/airport.jpg`) and a dataset of 15,793 objects with positions, footprints and heights. The dataset is authoritative; the picture is for display. Both cover 5000 m x 3500 m at 0.625 m/px. The dataset carries its own projection, operational boundary and a 500 m lettered grid (A-J x 1-7). Replacing the map: `assets/README.md`.

| Feature | Detail |
|---|---|
| Runways | Two; main runway 09R/27L is 2600 m |
| Terminal | 600 m building with piers and stands (`BLD-0001`, 20 m) |
| Control tower | 45 m, mid-field, the tallest object |
| Launch pads | HP-1 and HP-2, east apron. The only places the drone may take off. |
| Structures | 966 buildings, 17 aircraft, masts, silos, gantries, pylons |
| Scenery | 11,296 trees (up to 30 m), 2,423 cars, 325 crop fields |
| Beyond the boundary | Motorway, river, railway, solar farm, farmland. The boundary exists only in the rules. |

Operational area: a polygon of 9.97 km2 from the dataset.

### Launching

- Power-on is refused anywhere except a pad; the operator picks HP-1 or HP-2.
- A helicopter (3.5 m) is parked on HP-1. Objects within a pad's radius are not obstacles below a clearance height derived from the data (tallest object sharing the pad plus 2 m).

### Collision and boundary rules

- Any object with a height is an obstacle, tested against its real footprint (polygon, centreline with width for roads and fences, or rotated rectangle). Altitude is above ground, so an object is a hazard only below its height. Crop fields are excluded.
- Crossing the boundary or entering an obstacle below its height ends the flight. Detection is debounced: 5 consecutive control-loop ticks outside the boundary, 3 inside an obstacle.
- The checks use a 100 m spatial grid over all 15,793 objects at 10 Hz.
- The rules are enforced by the C2. An attacker who owns the C2 can lift them.

### Inventory

The **Inventory** tab is open to every role, observers included.

- Free text over id, type, use, species, model, stand, surface
- Filters: type, minimum height, inside or outside the operational area
- Search near a position with a radius. A pasted `lat, lon` splits into both fields. Results are nearest first, with distance measured to the object's footprint.
- Scenery (trees, fields, solar tables) hidden behind a toggle
- Filtering runs on the C2 (`GET /api/site/objects`); `GET /api/site/objects/at` answers what covers a point and whether it is in the way at a given altitude.

## Patrol routes

Selected from the **Patrol** dropdown.

| Key | Route | Covers | Length |
|---|---|---|---|
| `perimeter` | Operational area perimeter (default) | Boundary, held inside the line | 11.0 km |
| `runways` | Runway sweep | Both runways end to end | 5.5 km |
| `terminal` | Terminal & apron circuit | Terminal, stands, parked aircraft | 2.9 km |
| `approach` | Approach corridor | Main runway centreline, both approaches | 8.6 km |
| `pads` | Launch pad circuit | Box around HP-1 and HP-2 | 1.8 km |

- Routes are derived from dataset features. A test asserts each stays inside the area and clears every structure at patrol altitude, sampled every 25 m.
- Custom route: switch the toolbar to *Draw route* and click points; *Erase* removes them. Editing a predefined route sets the selector to *Custom*.
- The drone loops the route, advancing when within `PATROL_ARRIVE_M` (3 m).
- Auto-patrol: with `AUTO_PATROL=true` (default) the C2 powers the drone on at startup, climbs to `AUTO_PATROL_ALT` (60 m) and starts `AUTO_PATROL_ROUTE` (`perimeter`). Set `AUTO_PATROL=false` to boot idle.

## Flying

Controls, with screenshots: [OPERATOR-GUIDE.md](OPERATOR-GUIDE.md).

- The active target and patrol route (next waypoint marked) are broadcast to every signed-in user.
- Zoom runs from the whole site to about 3 cm/px; the drone is drawn at true size (about 1.6 m), with a marker at coarse zoom.
- With `DRONE_COUNT` above 1 the swarm controls appear.

## Losing the drone

The console reports signal loss identically whether the drone hit a structure or left the area:

```
[ERROR] Sentinel - SIGNAL LOST
        Last known position 43.99595, 25.00263 (grid F5) at 20 m. Position now unknown.
[WARN ] Telemetry stream interrupted - no frames received.
...
[ERROR] Sentinel is not responding. Airframe presumed lost.
```

- The sidebar shows `NO SIGNAL`; the readout switches to Last lat / lon / alt; the map shows a dashed question mark.
- The cause appears nowhere in the log, audit trail or public API.
- The audit entry:

```json
{"action": "SIGNAL_LOST",
 "params": {"last_known_lat": 43.995954, "last_known_lon": 25.002632,
            "last_known_alt_m": 20, "grid_ref": "F5",
            "ground_speed_ms": 7.9, "heading_deg": 258.7}}
```

- Inventory *near position* with that coordinate returns `Building - passenger terminal BLD-0001 20.0 m ... at this point`. A 20 m building against a 20 m last altitude identifies the cause. If nothing is there and the point is outside the boundary, the drone was flown away. The lookup uses the collision detector's footprint test.
- `GET /api/public/drone` returns `alive` or `missing`: `docs/PUBLIC-API.md`.

## Maintenance reset

**Reset Drone** (admins always; operators for a drone they hold) is the only way back from a write-off. A write-off refuses power-on.

| Cleared | Reason |
|---|---|
| Control loop, flight link | Stops current activity |
| Tampered parameters | Survive a power cycle otherwise |
| Partial mission uploads | Survive a power cycle otherwise |
| Telemetry subscribers on the radio link | Otherwise the drone keeps streaming to the attacker |
| Target, patrol route, claim, ERROR / SIGNAL_LOST state | Back to a known-good runtime |
| Airframe (after a write-off) | Replacement placed on a pad |

It then powers back up to `READY` and reports what it cleared. It does not clear the audit log or IDS alerts.

## Attack surface

| Surface | Weakness |
|---|---|
| `drone:14550/udp` | Unauthenticated MAVLink |
| `drone:9100/tcp` | Unauthenticated lifecycle API |
| `c2:8000/tcp` | Guessable JWT secret, no login rate limit, known console passwords |
| `/api/public/drone` | Unauthenticated; tells an attacker whether an attack worked |

Per-attack effects, the toolkit and mitigations: `docs/SECURITY.md`, `docs/ATTACKS.md`. Sensor: `docs/MONITORING.md`.
