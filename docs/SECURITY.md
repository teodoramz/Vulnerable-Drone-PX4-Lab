# Security lab

The lab is statically vulnerable; nothing is toggleable. The C2 enforces authentication, RBAC and claim/lock, but the drone speaks unauthenticated MAVLink and several surfaces are exposed on purpose.

## Premise

The attacker has compromised a DMZ host and pivoted onto `ot-ops` / `ot-air`. The ground station is outside and talks only to the C2 on `8000/tcp`; it is not an entry point. The sensor watches both internal segments.

## Vulnerabilities

| Weakness | Where | Exploited by | Detected by |
|---|---|---|---|
| Unauthenticated MAVLink commands | `drone:14550/udp` | `arm`, `disarm`, `kill`, `mode`, `rtl`, `reposition` | sid 9000001/9000021, 9000003/9000025, 9000015/9000024 |
| Unauthenticated position control | `drone:14550/udp` | `mavcrash`, `mavflyaway` | sid 9000014/9000023 |
| Unauthenticated GPS input | `drone:14550/udp` | `gpsspoof` | sid 9000004/9000026 (9000005/9000027 cover `HIL_GPS`) |
| Unauthenticated mission protocol | `drone:14550/udp` | `waypoint` | sid 9000013/9000030 (wipe); 9000006/9000028, 9000007/9000029 (upload) |
| Parameters writable over MAVLink | `drone:14550/udp` | `param` | sid 9000008/9000031 |
| No MAVLink rate limiting | `drone:14550/udp` | `flood` | sid 9000009/9000032 |
| Guessable JWT secret (HS256) | `c2:8000` | `jwtforge`, `takeover`, `hijack`, `crashinto`, `flyaway` | none; audit log |
| Console accounts with known passwords | `c2:8000` | `brute` | sid 9000010 |
| No login rate limiting | `c2:8000` | `brute` | sid 9000010 |
| Broad data exposure to admin tokens | `c2:8000` | `enum` | none; audit log |
| Unauthenticated lifecycle API | `drone:9100` | `dronepower` | sid 9000011 |
| Exposed services | all | `scan` | sid 9000012 |
| IDS alerts relayed through the C2 | `c2:8000` | Alert suppression after C2 compromise | `sensor:9200` is the out-of-band source |
| Unauthenticated status API | `c2:8000` `/api/public/drone` | Feedback on attack success | none (see `docs/PUBLIC-API.md`) |
| Operational area enforced C2-side only | `c2` | Lifted by an attacker who owns the C2 | audit log |

## Toolkit

`tools/exploit.py`. Each subcommand's `--help` names the rule class expected to catch it. Targets are explicit:

```bash
export C2_HOST=172.30.10.10 DRONE_HOST=172.30.20.10 MAVLINK_HOST=172.30.20.10
```

Per-flag overrides: `--c2-host`, `--drone-host`, `--mavlink-host`, `--mavlink-port` (default 14550), `--gcs-sysid` (default 255), `--udpin` / `--udpout`, `--blind`, `--objects`.

### MAVLink layer

```bash
python3 tools/exploit.py recon                    # passive: identify the vehicle
python3 tools/exploit.py sniff                    # passive: live telemetry
python3 tools/exploit.py kill                     # forced disarm (does not bring down PX4)
python3 tools/exploit.py mode --mode LAND
python3 tools/exploit.py gpsspoof --lat 44.4 --lon 28.1
python3 tools/exploit.py waypoint                 # wipe/overwrite the mission
python3 tools/exploit.py param --name GF_ACTION --value 0
python3 tools/exploit.py flood --seconds 10
python3 tools/exploit.py mavcrash --lat 43.9954186 --lon 24.9954419 --alt 27
python3 tools/exploit.py mavflyaway --overshoot 1.8
```

Also `arm`, `disarm`, `rtl`, `reposition`. Requires `pymavlink`.

Attach mode: PX4 broadcasts its GCS link on `14550/udp`. On the drone host the toolkit binds the port (`udpin`). From another host it dials out (`udpout`). It chooses by whether `--mavlink-host` is set; `--udpin` / `--udpout` force one.

### Application layer

```bash
python3 tools/exploit.py scan 172.30.10.0/24      # TCP service sweep, host or CIDR
python3 tools/exploit.py brute --user admin       # no rate limiting
python3 tools/exploit.py jwtforge                 # crack the secret, forge a token
python3 tools/exploit.py takeover                 # forged token, command the drone
python3 tools/exploit.py enum                     # fleet, users, audit log
python3 tools/exploit.py dronepower --off         # power off via :9100, no credentials
python3 tools/exploit.py hijack --route runways   # hold the controls on a chosen route
python3 tools/exploit.py crashinto                # see docs/ATTACKS.md
python3 tools/exploit.py flyaway
```

`jwtforge` uses stdlib HMAC only.

`tools/hijack.py` is a minimal MAVLink command-injection demo: `python tools/hijack.py [host] [port]` (env `HIJACK_IP`, `HIJACK_PORT`).

### Pivot container

See `docs/ATTACKS.md` ("Attacking from inside") for the attacker container and source-address attribution.

## Suggested exercise

1. `scan` the segment and map ports to components.
2. `recon` and `sniff` are passive and trip no rule; baseline the drone first.
3. Take the aircraft over the radio link: `kill`, `waypoint`, `mavcrash`, `mavflyaway`.
4. Take the platform: `brute` or `jwtforge`, then `enum`, `takeover`, `hijack`, `crashinto`, `flyaway`.
5. Open the Network tab. Establish which attacks the sensor caught and which it missed.
6. Suppress: with C2 access, hide alerts from the console, then compare against `sensor:9200`.
7. Recover with **Reset Drone** and check the Flows view for the attacker's telemetry subscription disappearing.

Network detection and audit-log review cover different attacks: `recon`, `sniff` and the C2-channel attacks (`takeover`, `hijack`, `crashinto`, `flyaway`) trip no rule.

## Mitigations

| Weakness | Control |
|---|---|
| Unauthenticated MAVLink | MAVLink 2 signing; keep the radio link off routable networks; segment `ot-air` |
| GPS spoofing | Multi-constellation / RTK cross-check; reject implausible position jumps |
| Mission tampering | Signed missions; reject mission writes while airborne |
| Flying the aircraft away | Geofence enforced on the vehicle, not only C2-side |
| Weak JWT secret | Long random `JWT_SECRET`; short token lifetime; rotation |
| No login rate limiting | Rate limit and lockout on auth endpoints |
| Unauthenticated lifecycle API | Authenticate it; expose only to the C2 |
| Broad data exposure | Least privilege per endpoint; restrict audit-log reads |
| Alerts through the C2 | Out-of-band alert path; ship `eve.json` to a SIEM the C2 cannot reach |
