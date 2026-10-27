# Public drone status API

Unauthenticated endpoint for exercise scorers and dashboards. It reports whether the aircraft is still in service and never reports why contact was lost.

```
GET http://<c2-host>:8000/api/public/drone
```

The same path is available through the ground station proxy at `http://<gcs-host>:8080/api/public/drone` (port 80 on an Ansible-deployed host). No token, header or cookie is needed. Responses are `application/json`.

## Responses

### `alive`

```json
{
  "drone_id": 0,
  "callsign": "Sentinel",
  "state": "alive",
  "since": "2026-10-03T11:33:30.227753+00:00",
  "flying": false
}
```

| Field | Meaning |
|---|---|
| `drone_id` | `0` in the single-drone scenario |
| `callsign` | `Sentinel` |
| `state` | `"alive"` |
| `since` | ISO-8601 UTC. When this airframe entered service. |
| `flying` | `true` only while powered on and airborne |

`alive` covers never deployed, powered on on the pad, and airborne.

### `missing`

```json
{
  "drone_id": 0,
  "callsign": "Sentinel",
  "state": "missing",
  "last_known": { "lat": 43.994092, "lon": 25.011229, "alt_m": 13.6 },
  "last_contact": "2026-10-03T11:09:25.068870+00:00"
}
```

| Field | Meaning |
|---|---|
| `state` | `"missing"` |
| `last_known.lat` / `.lon` | Last fix, 6 decimal places |
| `last_known.alt_m` | Last altitude above ground, 1 decimal place |
| `last_contact` | ISO-8601 UTC. When telemetry stopped. |

- `since` and `flying` are absent when `missing`; `last_known` and `last_contact` are absent when `alive`. Read `state` first.
- Values inside `last_known` are `null` if contact was lost before any position was received.

### `503`

```json
{ "detail": "Fleet not started" }
```

Returned briefly after C2 boot, before the drone registry is loaded. Retry.

## Behaviour

- There is no `crashed`, `destroyed`, `out_of_area` or cause field. A structure strike and a boundary crossing are reported identically. The cause is kept internally and is not served on an unauthenticated endpoint. See `docs/ATTACKS.md` for the investigation path.
- Only a maintenance reset returns `missing` to `alive`. It places a replacement on HP-1 or HP-2 and sets a new `since`. Powering on is refused while the aircraft is missing, so `state` does not revert on its own.

## Fleet form

```
GET /api/public/drones
```

```json
{ "drones": [ { "drone_id": 0, "callsign": "Sentinel", "state": "alive", "since": "...", "flying": false } ] }
```

Each element is the object `/api/public/drone` returns. The single-drone endpoint reports the lowest `drone_id`.

## Scoring examples

```bash
curl -s http://<c2-host>:8000/api/public/drone | jq -r .state

# last known position, for the Inventory search
curl -s http://<c2-host>:8000/api/public/drone \
  | jq -r '.last_known | "\(.lat), \(.lon) at \(.alt_m) m"'

# poll, tolerating the 503 window during a C2 restart
while true; do
  s=$(curl -s --max-time 3 http://<c2-host>:8000/api/public/drone | jq -r '.state // "unknown"')
  printf '%s  %s\n' "$(date -u +%H:%M:%SZ)" "$s"; sleep 10
done
```

```python
import urllib.request, json

def drone_state(host: str) -> dict:
    try:
        with urllib.request.urlopen(f"http://{host}:8000/api/public/drone", timeout=3) as r:
            return json.load(r)
    except Exception:
        return {"state": "unknown"}   # client-side value; the API only returns alive or missing
```

## Security note

An attacker can poll the same endpoint to learn whether an attack worked. See `docs/SECURITY.md`.
