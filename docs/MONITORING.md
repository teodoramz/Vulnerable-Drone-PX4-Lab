# Monitoring

The `sensor` component is Suricata (af-packet) on both internal segments plus a FastAPI sidecar that tails `eve.json`, keeps rolling buffers and serves them on `:9200`.

```
ot-ops, ot-air --> Suricata --> eve.json --> sidecar :9200
ot-ops, ot-air --> AF_PACKET tap (livetap.py) --> sidecar :9200
sidecar --POST /api/ids/alerts--> c2 --/ws--> console              (alerts)
c2 --GET /live /packets /breakdown /captures--> sidecar            (proxied as /api/ids/*)
sidecar --/alerts /flows /ws--> SIEM                               (independent of c2)
```

## Capture

- Containers on a Docker bridge cannot see other containers' traffic. The sensor runs `network_mode: host` with `NET_ADMIN` and `NET_RAW` and captures on the bridge interfaces `ot-ops` and `ot-air`. The bridges are named through `com.docker.network.bridge.name`.
- On a dedicated sensor VM those bridges do not exist. Set `SENSOR_IFACES` to the NIC that receives mirrored traffic (for example `eth1`).
- If Suricata exits, the container exits.

## Ruleset

`services/sensor/rules/drone-ot.rules`, sids 9000001-9000032. Suricata has no MAVLink
parser, so MAVLink rules match raw byte offsets. v1 and v2 put the msgid at different
offsets, so each MAVLink detection has two sids with one name: 9000001-9000015 for v2,
9000021-9000032 for v1.

| sid (v2 / v1) | Detects | Tripped by | Threshold (per source) |
|---|---|---|---|
| 9000001 / 9000021 | `COMMAND_LONG` from non-C2 source | `arm`, `disarm`, `kill`, `mode`, `rtl` | 3 / 10 s |
| 9000002 / 9000022 | `SET_MODE` from non-C2 source | not sent by this toolkit | 3 / 10 s |
| 9000003 / 9000025 | Forced disarm (21196 in param2) | `kill` | 3 / 10 s |
| 9000004 / 9000026 | `GPS_INPUT` injected | `gpsspoof` | 3 / 10 s |
| 9000005 / 9000027 | `HIL_GPS` injected | not sent by this toolkit | 3 / 10 s |
| 9000006 / 9000028 | `MISSION_COUNT` from non-C2 source | not sent by this toolkit | 3 / 10 s |
| 9000007 / 9000029 | `MISSION_ITEM_INT` from non-C2 source | not sent by this toolkit | 3 / 10 s |
| 9000008 / 9000031 | `PARAM_SET` from non-C2 source | `param`, `kill` | 3 / 10 s |
| 9000009 / 9000032 | MAVLink flood to the GCS link | `flood`, `mavcrash`, `mavflyaway` | 100 / 5 s |
| 9000013 / 9000030 | `MISSION_CLEAR_ALL` | `waypoint` | 3 / 10 s |
| 9000014 / 9000023 | Position setpoint from non-C2 source | `mavcrash`, `mavflyaway` | 2 / 10 s |
| 9000015 / 9000024 | `COMMAND_INT` from non-C2 source | `reposition` | 2 / 10 s |
| 9000010 | Repeated `POST /api/auth/login` | `brute` | 5 / 10 s |
| 9000011 | Unauthenticated access to `drone:9100` | `dronepower` | 3 / 10 s |
| 9000012 | TCP port sweep on an OT segment | `scan` | 15 / 5 s |

- Per-packet rules use `threshold: type limit, track by_src` so a flood does not evict other alerts from the buffer. The flood and scan rules use `type both`.
- Not detected by any rule: `recon`, `sniff`, and the C2-channel attacks (`takeover`, `hijack`, `crashinto`, `flyaway`). Evidence for the last four is in the audit log.
- pymavlink sends v1 until the peer answers in v2: against PX4 with `--blind` the v1
  sids fire, against the mock the v2 sids.
- 9000012 fires only for a sweep between two OT addresses (e.g. from the attacker
  container), not from outside the lab.
- 9000010 needs 5 logins in 10 s. `brute` tries `Admin1Admin1` first and succeeds at
  once; use `--wordlist` without it to trip the rule.
- MAVLink header layouts used by the rules. v2: byte 0 magic `0xFD`, 1 len, 2 incompat
  flags, 3 compat flags, 4 seq, 5 sysid, 6 compid, 7-9 msgid (24-bit LE), 10+ payload.
  v1: byte 0 magic `0xFE`, 1 len, 2 seq, 3 sysid, 4 compid, 5 msgid, 6+ payload.
- A wrong offset loads and passes `suricata -T` but never fires. `depth` counts from `offset` and must equal the pattern length, or the rule fires on other messages. After editing a MAVLink rule run the pcap regression test (requires Suricata):

```bash
cd services/sensor && pytest tests/test_rules_against_pcap.py -v
```

`tests/fixtures/mavlink-attacks.pcap` (regenerate with `tests/fixtures/make_pcap.py`)
holds pymavlink attack frames in both wire formats and HEARTBEAT decoys carrying every
rule's msgid. The test checks both formats fire and each alert matches its frame.

## Network tab

Four views. Only the visible view polls (2 s).

| View | Content | Sensor endpoint | C2 proxy |
|---|---|---|---|
| Alerts | Severity tiles, alert stream, filters, per-alert detail with annotated hex dump of the matching packet | `GET /alerts` | `GET /api/ids/alerts` |
| Flows | Per-flow packet and byte counters over a rolling 60 s window; *unknown peers* filter | `GET /live` (`GET /flows` is Suricata's flow log) | `GET /api/ids/live`, `GET /api/ids/flows` |
| Packets | Recent packets with decoded MAVLink message and system id; `MAVLink only` and `freeze`; click for the first 64 bytes | `GET /packets` | `GET /api/ids/packets` |
| Breakdown | Share by protocol and service port, MAVLink message mix, pcap list and download | `GET /breakdown`, `GET /captures`, `GET /captures/{name}` | `GET /api/ids/breakdown`, `/captures`, `/captures/{name}` |

Notes:

- Flows and Packets come from the sensor's own raw `AF_PACKET` tap (`services/sensor/app/livetap.py`), not from Suricata, because Suricata emits a flow record only after a flow ends and the telemetry stream never ends. The tap counts and decodes headers only; Suricata alone decides what is an attack.
- Packet decoding reads fixed header offsets and does not use pymavlink. An undecodable packet has no MAVLink annotation.
- Breakdown attributes traffic to the lower of the two port numbers.
- `GET /api/ids/alerts?limit=&severity=` is open to every authenticated role.
- Baseline: C2 to drone traffic is about 20 packets/s. A new peer on `14550/udp` receiving telemetry is an attacker subscribed to the link; a maintenance reset removes it.

## Packet capture

Rotating pcap, `conditional: all` (every packet, not only alerted ones), 32 MB x 8 files, written to `./captures/` on the host (gitignored, `ot-lab.pcap.<unix-ts>`).

```bash
ls captures/
wireshark captures/ot-lab.pcap.<ts>
curl -s localhost:9200/captures        # metadata only
```

Files are also downloadable from the Breakdown view. The name must start with `ot-lab.pcap` and contain no path separator.

## Flow timeouts

`suricata.yaml` shortens flow timeouts (UDP established 20 s, new 5 s; stock is 300 s) so the traffic views populate quickly. This suits a training range, not a production sensor.

## Alert path and its weakness

Alerts reach the console through the C2 so that only one port crosses the boundary. An attacker who owns the C2 can suppress what operators see. `sensor:9200` and `eve.json` are independent of the C2.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `SENSOR_IFACES` | `ot-ops,ot-air` | Interfaces to capture on |
| `EVE_PATH` | `/var/log/suricata/eve.json` | Suricata output read by the sidecar |
| `C2_URL` | `http://127.0.0.1:8000` | Alert push target. Not `http://c2:8000`: host networking has no Docker DNS. |
| `IDS_PUSH_TOKEN` | `ids-dev-token` | Shared secret for `POST /api/ids/alerts` (`X-IDS-Token`) |
| `ALERT_BUFFER_SIZE` | `2000` | Sidecar alert buffer |
| `IDS_BUFFER_SIZE` | `500` | C2 alert buffer |
| `SENSOR_URL` | `http://172.30.10.1:9200` | Where the C2 pulls live traffic from |
| `HOME_NET`, `C2_HOST_ADDR`, `DRONE_HOST_ADDR` | `[172.30.0.0/16]`, `[172.30.10.10/32,172.30.20.11/32]`, `[172.30.20.10/32]` | Rule address variables |

If `C2_HOST_ADDR` or `DRONE_HOST_ADDR` is not supplied, the rules use placeholder TEST-NET-3 addresses (203.0.113.0/24) that match nothing, and the entrypoint prints a warning.

## SIEM

`eve.json` is standard EVE JSON (`alert` and `flow` events). Mount the log directory or consume the sidecar `WS /ws`. Both are independent of the C2.

## Tuning

Watch `/live` with the lab idle to learn the baseline. Tighten rules that fire on the baseline first.
