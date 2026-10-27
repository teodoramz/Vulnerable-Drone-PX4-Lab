#!/usr/bin/env bash
# Sensor entrypoint: renders the af-packet interfaces (SENSOR_IFACES) and rule
# addresses (HOME_NET / C2_HOST / DRONE_HOST) at runtime, then starts Suricata
# and the FastAPI sidecar that tails eve.json.
set -euo pipefail

SENSOR_IFACES="${SENSOR_IFACES:-ot-ops,ot-air}"
EVE_PATH="${EVE_PATH:-/var/log/suricata/eve.json}"
HOME_NET="${HOME_NET:-[172.16.0.0/12,192.168.0.0/16,10.0.0.0/8]}"
C2_HOST_ADDR="${C2_HOST_ADDR:-${C2_ADDR:-}}"
DRONE_HOST_ADDR="${DRONE_HOST_ADDR:-${DRONE_ADDR:-}}"
IFACE_WAIT_SECS="${IFACE_WAIT_SECS:-60}"
SURICATA_YAML="${SURICATA_YAML:-/etc/suricata/suricata.yaml}"

LOG_DIR="$(dirname "$EVE_PATH")"
# Suricata will not start if the pcap-log dir is missing.
mkdir -p "$LOG_DIR" "$LOG_DIR/captures"

IFS=',' read -ra IFACES <<< "$SENSOR_IFACES"
if [ "${#IFACES[@]}" -eq 0 ]; then
    echo "sensor: SENSOR_IFACES is empty - nothing to capture on." >&2
    exit 1
fi

# The docker bridges appear only after the other services are up.
echo "sensor: waiting for capture interfaces: ${IFACES[*]}"
deadline=$(( SECONDS + IFACE_WAIT_SECS ))
for iface in "${IFACES[@]}"; do
    iface="$(echo "$iface" | xargs)"
    while [ ! -e "/sys/class/net/${iface}" ]; do
        if [ "$SECONDS" -ge "$deadline" ]; then
            echo "sensor: interface '${iface}' never appeared after ${IFACE_WAIT_SECS}s." >&2
            echo "sensor: on a single host these are the named docker bridges" >&2
            echo "sensor:   (ot-ops/ot-air) and need network_mode: host." >&2
            echo "sensor: on a dedicated VM set SENSOR_IFACES to the real NIC." >&2
            exit 1
        fi
        sleep 1
    done
    echo "sensor:   ${iface} is up"
done

# Render af-packet explicitly: `--set af-packet.1.*` creates a half-initialised
# entry and Suricata segfaults with more than one interface.
RUNTIME_YAML=/tmp/suricata.runtime.yaml
python3 - "$SURICATA_YAML" "$RUNTIME_YAML" "$SENSOR_IFACES" "${AF_PACKET_BLOCK_SIZE:-1048576}" <<'PY'
import sys

template, out, ifaces_csv, block_size = sys.argv[1:5]
ifaces = [i.strip() for i in ifaces_csv.split(",") if i.strip()]

lines = open(template).read().splitlines(keepends=True)
start = next(i for i, l in enumerate(lines) if l.startswith("af-packet:"))
# The block ends at the first non-blank, non-indented line (including comments).
end = start + 1
while end < len(lines):
    l = lines[end]
    if l.strip() and not l[0].isspace():
        break
    end += 1

block = ["af-packet:\n"]
for n, iface in enumerate(ifaces):
    block += [
        f"  - interface: {iface}\n",
        "    threads: 1\n",
        f"    cluster-id: {99 - n}\n",
        "    cluster-type: cluster_flow\n",
        "    defrag: yes\n",
        "    use-mmap: yes\n",
        "    tpacket-v3: yes\n",
        # Must hold at least one frame; the default is rejected on high-MTU interfaces.
        f"    block-size: {block_size}\n",
    ]

open(out, "w").writelines(lines[:start] + block + lines[end:])
print(f"sensor: rendered af-packet for {len(ifaces)} interface(s): {', '.join(ifaces)}")
PY

SURICATA_ARGS=(--af-packet -c "$RUNTIME_YAML" -S /etc/suricata/rules/drone-ot.rules)
SURICATA_ARGS+=(--set "vars.address-groups.HOME_NET=${HOME_NET}")
[ -n "$C2_HOST_ADDR" ] && SURICATA_ARGS+=(--set "vars.address-groups.C2_HOST=${C2_HOST_ADDR}")
[ -n "$DRONE_HOST_ADDR" ] && SURICATA_ARGS+=(--set "vars.address-groups.DRONE_HOST=${DRONE_HOST_ADDR}")

if [ -z "$C2_HOST_ADDR" ] || [ -z "$DRONE_HOST_ADDR" ]; then
    echo "sensor: WARNING - C2_HOST_ADDR/DRONE_HOST_ADDR not set; the ruleset's"
    echo "sensor: placeholder addresses (203.0.113.0/24, TEST-NET-3) will match"
    echo "sensor: nothing real. Peer-identity rules will not fire."
fi

echo "sensor: starting suricata on ${IFACES[*]}"
suricata "${SURICATA_ARGS[@]}" &
SURICATA_PID=$!

echo "sensor: starting alert API on :9200"
uvicorn app.main:app --host 0.0.0.0 --port 9200 &
API_PID=$!

cleanup() {
    kill -TERM "$SURICATA_PID" "$API_PID" 2>/dev/null || true
}
trap cleanup EXIT SIGINT SIGTERM

# Exit if either process dies: a blind sensor must not keep answering /health.
# Both are children of this shell, which `wait -n` requires.
wait -n "$SURICATA_PID" "$API_PID"
EXITED=$?

if ! kill -0 "$SURICATA_PID" 2>/dev/null; then
    echo "sensor: suricata exited (status ${EXITED}) -- the sensor is blind, stopping." >&2
else
    echo "sensor: alert API exited (status ${EXITED}) -- stopping." >&2
fi
cleanup
exit 1
