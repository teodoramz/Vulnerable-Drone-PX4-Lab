#!/usr/bin/env bash
# Drone entrypoint: builds PX4 once, starts DDS and the MAVLink relay to the C2,
# then serves the lifecycle agent API. PX4 runs as SIH (no Gazebo).
set -e
trap "kill 0" EXIT SIGINT SIGTERM

cd /app

# Start position for SIH; the C2 relocates the drone to the chosen helipad on power-on.
export PX4_HOME_LAT="${HOME_LAT:-43.9977991}"
export PX4_HOME_LON="${HOME_LON:-25.0154851}"
export PX4_HOME_ALT="${HOME_ALT:-95.0}"
export PX4_SIM_SPEED_FACTOR=1

# PX4-Autopilot lives on a persistent volume, so detect a checkout by its Makefile.
# No credential prompts (no TTY). Clone non-recursively and fetch submodules
# serially, since GitHub rate-limits parallel submodule fetches.
export GIT_TERMINAL_PROMPT=0

# An interrupted fetch leaves a submodule whose HEAD does not resolve, and every
# later update refuses it. Finish the fetch and check out the recorded commit.
repair_submodules() {
    git config -f .gitmodules --get-regexp '\.path$' 2>/dev/null | while read -r _ dir; do
        [ -f "$dir/.git" ] || continue
        if ! git -C "$dir" rev-parse -q --verify HEAD >/dev/null 2>&1; then
            sha=$(git rev-parse "HEAD:$dir")
            echo "Finishing half-fetched submodule $dir"
            git -C "$dir" fetch -q origin "$sha" || git -C "$dir" fetch -q origin || continue
            git -C "$dir" checkout -q -f "$sha" || continue
        fi
        (cd "$dir" && repair_submodules)
    done
}

if [ ! -f "PX4-Autopilot/Makefile" ]; then
    echo "Cloning PX4-Autopilot (release/1.14)..."
    find PX4-Autopilot -mindepth 1 -delete 2>/dev/null || true   # clear partial/empty volume contents
    n=0; until [ "$n" -ge 5 ]; do
        git clone -b release/1.14 https://github.com/PX4/PX4-Autopilot.git PX4-Autopilot && break
        n=$((n+1)); echo "clone retry $n/5..."; sleep 15
    done
fi

if [ ! -f "PX4-Autopilot/build/px4_sitl_default/bin/px4" ]; then
    echo "Fetching submodules serially..."
    (cd PX4-Autopilot
     n=0
     until repair_submodules; git submodule update --init --recursive --jobs 1; do
        n=$((n+1))
        [ "$n" -lt 10 ] || { echo "Submodule fetch failed 10 times."; exit 1; }
        echo "submodule retry $n/10..."; sleep 20
     done)
    echo "Compiling PX4 firmware (first run - this takes ~20-40 min)..."
    (cd PX4-Autopilot && HEADLESS=1 make px4_sitl)
fi

echo "Wiping stale instance memory..."
rm -rf PX4-Autopilot/build/px4_sitl_default/instance_*

# SIH ignores PX4_HOME_*; its origin is the SIH_LOC_* params. Inject them into the
# built airframe (idempotent) to avoid a recompile.
AIRFRAME="PX4-Autopilot/build/px4_sitl_default/etc/init.d-posix/airframes/10040_sihsim_quadx"
if [ -f "$AIRFRAME" ]; then
    LAT0=$(python3 -c "print(round(${PX4_HOME_LAT} * 1e7))")
    LON0=$(python3 -c "print(round(${PX4_HOME_LON} * 1e7))")
    sed -i '/# >>> lab-home/,/# <<< lab-home/d' "$AIRFRAME"
    cat >> "$AIRFRAME" <<EOF
# >>> lab-home (injected by entrypoint from HOME_*)
param set-default SIH_LOC_LAT0 ${LAT0}
param set-default SIH_LOC_LON0 ${LON0}
param set-default SIH_LOC_H0 ${PX4_HOME_ALT}
# <<< lab-home
EOF
    echo "SIH world origin set to ${PX4_HOME_LAT}, ${PX4_HOME_LON} (${LAT0}, ${LON0})."
fi

# DELIBERATE VULNERABILITY: an unauthenticated MAVLink radio link on 14550.
# `-u` binds the port and `-p` broadcasts telemetry, as a radio link would.
# Patched into the built config, no recompile needed.
RADIO_PORT="${RADIO_LINK_PORT:-14550}"
RC_MAVLINK="PX4-Autopilot/build/px4_sitl_default/etc/init.d-posix/px4-rc.mavlink"
if [ -f "$RC_MAVLINK" ]; then
    sed -i '/# >>> lab-radio/,/# <<< lab-radio/d' "$RC_MAVLINK"
    cat >> "$RC_MAVLINK" <<EOF
# >>> lab-radio (injected by entrypoint - the deliberately exposed link)
mavlink start -x -u \$((${RADIO_PORT}+px4_instance)) -r 4000000 -f -p
# <<< lab-radio
EOF
    echo "Exposed radio link on ${RADIO_PORT}/udp (unauthenticated, by design)."
fi

echo "Starting Micro-XRCE-DDS Agent..."
MicroXRCEAgent udp4 -p 8888 &
sleep 2

echo "Starting MAVLink relay -> ${C2_HOST:-c2}..."
/app/px4/start_relays.sh "${C2_HOST:-c2}" "${DRONE_COUNT:-1}" "${PX4_MAVLINK_BASE_PORT:-14540}" &

echo "Starting PX4 lifecycle agent on :9100..."
exec uvicorn app.main:app --host 0.0.0.0 --port 9100
