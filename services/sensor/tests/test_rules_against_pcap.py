"""Replay a captured MAVLink attack pcap through the real ruleset.

The rules match raw MAVLink byte offsets, so a wrong offset loads fine and
never fires. The fixture holds pymavlink-generated attack frames in both wire
formats, because the two have different header lengths and so need separate
rules, plus decoys that carry every rule's msgid in their payload; regenerate
it with fixtures/make_pcap.py.

Skipped when suricata is not installed.
"""
from __future__ import annotations

import json
import re
import shutil
import struct
import subprocess
from pathlib import Path

import pytest

SENSOR_DIR = Path(__file__).resolve().parent.parent
PCAP = SENSOR_DIR / "tests" / "fixtures" / "mavlink-attacks.pcap"
RULES = SENSOR_DIR / "rules" / "drone-ot.rules"
CONFIG = SENSOR_DIR / "suricata.yaml"

# The message each MAVLink rule is about, by sid. Rate rules are absent.
MSGID = {
    9000001: 76, 9000021: 76,    # COMMAND_LONG
    9000002: 11, 9000022: 11,    # SET_MODE
    9000003: 76, 9000025: 76,    # forced disarm, a COMMAND_LONG
    9000004: 232, 9000026: 232,  # GPS_INPUT
    9000005: 113, 9000027: 113,  # HIL_GPS
    9000006: 44, 9000028: 44,    # MISSION_COUNT
    9000007: 73, 9000029: 73,    # MISSION_ITEM_INT
    9000008: 23, 9000031: 23,    # PARAM_SET
    9000013: 45, 9000030: 45,    # MISSION_CLEAR_ALL
    9000014: 86, 9000023: 86,    # SET_POSITION_TARGET_GLOBAL_INT
    9000015: 75, 9000024: 75,    # COMMAND_INT
}

pytestmark = pytest.mark.skipif(
    shutil.which("suricata") is None, reason="suricata not installed"
)


@pytest.fixture(scope="module")
def alerts(tmp_path_factory) -> list[dict]:
    """Run suricata over the fixture pcap and return the parsed alerts."""
    out = tmp_path_factory.mktemp("suricata-pcap")
    # pcap-log needs a `captures` subdirectory.
    (out / "captures").mkdir(exist_ok=True)
    # The drone is the destination; the attacker is anything else.
    subprocess.run(
        [
            "suricata", "-r", str(PCAP),
            "-c", str(CONFIG), "-S", str(RULES),
            "-l", str(out),
            "--set", "vars.address-groups.HOME_NET=[172.18.0.0/16]",
            "--set", "vars.address-groups.C2_HOST=[172.18.0.99/32]",
            "--set", "vars.address-groups.DRONE_HOST=[172.18.0.2/32]",
        ],
        check=True,
        capture_output=True,
        timeout=120,
    )
    eve = out / "eve.json"
    assert eve.exists(), "suricata produced no eve.json"
    found = []
    for line in eve.read_text().splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        if rec.get("event_type") == "alert":
            found.append(rec)
    return found


def _sids(alerts: list[dict]) -> set[int]:
    return {a["alert"]["signature_id"] for a in alerts}


def _frames() -> list[bytes]:
    """The fixture's MAVLink frames, indexed by pcap_cnt - 1."""
    data = PCAP.read_bytes()
    frames, off = [], 24
    while off < len(data):
        caplen = struct.unpack_from("<I", data, off + 8)[0]
        frames.append(data[off + 16 + 42:off + 16 + caplen])  # past Ethernet/IPv4/UDP
        off += 16 + caplen
    return frames


def _decode(frame: bytes) -> tuple[str, int]:
    """Wire format and msgid of a frame."""
    if frame[0] == 0xFD:
        return "v2", int.from_bytes(frame[7:10], "little")
    return "v1", frame[5]


def test_pcap_produces_alerts(alerts):
    assert alerts, "the attack pcap tripped no rules at all - offsets are wrong"


@pytest.mark.parametrize(
    ("sid", "what"),
    [
        (9000001, "v2 COMMAND_LONG from a non-C2 source"),
        (9000002, "v2 SET_MODE from a non-C2 source"),
        (9000003, "v2 forced disarm, the 21196 kill magic"),
        (9000004, "v2 GPS_INPUT injection"),
        (9000005, "v2 HIL_GPS injection"),
        (9000006, "v2 MISSION_COUNT from a non-C2 source"),
        (9000007, "v2 MISSION_ITEM_INT from a non-C2 source"),
        (9000008, "v2 PARAM_SET from a non-C2 source"),
        (9000013, "v2 MISSION_CLEAR_ALL"),
        (9000014, "v2 position setpoint injection"),
        (9000015, "v2 COMMAND_INT reposition"),
        (9000021, "v1 COMMAND_LONG from a non-C2 source"),
        (9000022, "v1 SET_MODE from a non-C2 source"),
        (9000023, "v1 position setpoint injection"),
        (9000024, "v1 COMMAND_INT reposition"),
        (9000025, "v1 forced disarm, the 21196 kill magic"),
        (9000026, "v1 GPS_INPUT injection"),
        (9000027, "v1 HIL_GPS injection"),
        (9000028, "v1 MISSION_COUNT from a non-C2 source"),
        (9000029, "v1 MISSION_ITEM_INT from a non-C2 source"),
        (9000030, "v1 MISSION_CLEAR_ALL"),
        (9000031, "v1 PARAM_SET from a non-C2 source"),
    ],
)
def test_expected_rule_fires(alerts, sid, what):
    assert sid in _sids(alerts), (
        f"rule {sid} ({what}) did not fire on real MAVLink frames. "
        f"Fired instead: {sorted(_sids(alerts))}"
    )


def test_both_wire_formats_are_covered(alerts):
    """A v2-only ruleset still passes every v2 case, so assert v1 too."""
    fired = _sids(alerts)
    assert fired & set(range(9000001, 9000016)), "no v2 rule fired"
    assert fired & set(range(9000021, 9000033)), "no v1 rule fired"


def test_every_alert_names_the_frame_that_tripped_it(alerts):
    """The decoys catch a `depth` that reaches past the msgid into the payload."""
    frames = _frames()
    decoys = sum(1 for f in frames if _decode(f)[1] == 0)
    assert decoys >= 7, "fixture has no decoy frames; regenerate it"
    wrong = []
    for a in alerts:
        sid = a["alert"]["signature_id"]
        if sid not in MSGID:
            continue
        got = _decode(frames[a["pcap_cnt"] - 1])
        want = ("v2" if sid < 9000021 else "v1", MSGID[sid])
        if got != want:
            wrong.append(f"sid {sid} fired on a {got[0]} msgid {got[1]} frame")
    assert not wrong, "\n".join(wrong)


def test_kill_alert_is_high_severity(alerts):
    kills = [a for a in alerts
             if a["alert"]["signature_id"] in (9000003, 9000025)]
    assert kills, "no forced-disarm alert to check"
    # Severity 1 is the most urgent.
    assert all(a["alert"]["severity"] == 1 for a in kills)


def test_alerts_carry_the_fields_the_c2_contract_needs(alerts):
    """Every field the C2's IdsAlertIn requires must be present in eve.json."""
    for a in alerts:
        assert a.get("timestamp")
        assert a["alert"].get("signature")
        assert a["alert"].get("signature_id")
        assert a["alert"].get("severity")
        assert a.get("src_ip") and a.get("dest_ip")
        assert a.get("proto")


def test_every_rule_loads(tmp_path):
    """Every rule must load; Suricata silently skips malformed ones, so assert the `-T` count."""
    expected = len([
        line for line in RULES.read_text().splitlines()
        if line.strip().startswith("alert ")
    ])
    assert expected > 0, "no rules found in the ruleset"

    (tmp_path / "captures").mkdir(exist_ok=True)
    proc = subprocess.run(
        ["suricata", "-T", "-c", str(CONFIG), "-S", str(RULES),
         "-l", str(tmp_path), "-v"],
        capture_output=True, text=True, timeout=120,
    )
    out = proc.stdout + proc.stderr
    m = re.search(r"(\d+) rules successfully loaded, (\d+) rules failed", out)
    assert m, f"could not parse suricata's rule-load summary from:\n{out}"
    loaded, failed = int(m.group(1)), int(m.group(2))

    assert failed == 0, f"{failed} rule(s) failed to load:\n{out}"
    assert loaded == expected, (
        f"{expected} 'alert' lines in the ruleset but suricata loaded {loaded}"
    )
