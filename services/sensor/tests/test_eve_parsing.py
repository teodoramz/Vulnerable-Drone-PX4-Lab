import json

from app.eve import parse_eve_line
from app.models import Alert, Flow

ALERT_LINE = json.dumps({
    "timestamp": "2026-09-21T04:20:00.123456+0000",
    "event_type": "alert",
    "src_ip": "172.20.0.50",
    "src_port": 51820,
    "dest_ip": "172.20.0.10",
    "dest_port": 14550,
    "proto": "UDP",
    "in_iface": "ot-air",
    "alert": {
        "action": "allowed",
        "gid": 1,
        "signature_id": 9000003,
        "rev": 1,
        "signature": "DRONE-OT MAVLink forced DISARM (kill magic 21196 in param2)",
        "category": "",
        "severity": 1,
    },
})

FLOW_LINE = json.dumps({
    "timestamp": "2026-09-21T04:20:05.000000+0000",
    "event_type": "flow",
    "src_ip": "172.20.0.50",
    "src_port": 51820,
    "dest_ip": "172.20.0.10",
    "dest_port": 14550,
    "proto": "UDP",
    "in_iface": "ot-air",
    "flow": {
        "pkts_toserver": 42,
        "pkts_toclient": 0,
        "bytes_toserver": 1890,
        "bytes_toclient": 0,
        "start": "2026-09-21T04:20:00.000000+0000",
        "end": "2026-09-21T04:20:05.000000+0000",
        "state": "new",
    },
})


def test_parse_alert_line_maps_to_contract_shape():
    record = parse_eve_line(ALERT_LINE)
    assert isinstance(record, Alert)
    assert record.ts == "2026-09-21T04:20:00.123456+0000"
    assert record.signature == "DRONE-OT MAVLink forced DISARM (kill magic 21196 in param2)"
    assert record.sid == 9000003
    assert record.severity == 1
    assert record.src_ip == "172.20.0.50"
    assert record.src_port == 51820
    assert record.dest_ip == "172.20.0.10"
    assert record.dest_port == 14550
    assert record.proto == "UDP"
    assert record.iface == "ot-air"


def test_parse_flow_line_maps_to_flow_model():
    record = parse_eve_line(FLOW_LINE)
    assert isinstance(record, Flow)
    assert record.pkts_toserver == 42
    assert record.bytes_toserver == 1890
    assert record.state == "new"
    assert record.iface == "ot-air"


def test_unknown_event_type_returns_none():
    line = json.dumps({"timestamp": "x", "event_type": "stats"})
    assert parse_eve_line(line) is None


def test_malformed_json_returns_none_without_raising():
    assert parse_eve_line("{not valid json") is None


def test_blank_line_returns_none():
    assert parse_eve_line("\n") is None
    assert parse_eve_line("   ") is None


def test_alert_missing_required_field_returns_none_not_raises():
    broken = json.dumps({"timestamp": "x", "event_type": "alert", "alert": {}})
    assert parse_eve_line(broken) is None


def test_iface_falls_back_to_default_when_not_in_event():
    line = json.dumps({
        "timestamp": "x",
        "event_type": "alert",
        "src_ip": "1.1.1.1", "dest_ip": "2.2.2.2", "proto": "UDP",
        "alert": {"signature_id": 1, "signature": "s", "severity": 2},
    })
    record = parse_eve_line(line, default_iface="ot-ops")
    assert record.iface == "ot-ops"
