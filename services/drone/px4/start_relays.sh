#!/usr/bin/env bash
# Launch one UDP MAVLink relay per drone, forwarding PX4 instance i's offboard
# link (127.0.0.1:BASE+i) to the C2 (C2_HOST:BASE+i).
C2_HOST="${1:-c2}"
COUNT="${2:-1}"
BASE="${3:-14540}"

for i in $(seq 0 $((COUNT - 1))); do
    port=$((BASE + i))
    echo "  relay 127.0.0.1:${port} <-> ${C2_HOST}:${port}"
    python3 /app/app/px4/relay.py "${port}" "${C2_HOST}" "${port}" &
done

wait
