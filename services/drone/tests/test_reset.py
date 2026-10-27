"""Maintenance reset clears what a power cycle leaves behind."""
from __future__ import annotations

from app.mavlink.params import DEFAULT_PARAMS
from app.mavlink.transport import MavlinkTransport
from app.mock.simulator import MockSimulator, SimDrone


def _sim() -> MockSimulator:
    return MockSimulator([SimDrone(id=0, callsign="Sentinel",
                                   home_lat=44.3222, home_lon=28.0553, home_alt=25.0)])


def test_reset_restores_tampered_parameters():
    t = MavlinkTransport(_sim())
    table = t._table_for(0)
    table["NAV_DLL_ACT"] = 99.0          # as a `param` attack would leave it
    table["RTL_RETURN_ALT"] = 1.0

    out = t.reset_drone(0)

    assert sorted(out["params_restored"]) == ["NAV_DLL_ACT", "RTL_RETURN_ALT"]
    assert t._table_for(0) == DEFAULT_PARAMS, "params were not restored to defaults"


def test_reset_reports_nothing_when_params_are_untouched():
    t = MavlinkTransport(_sim())
    t._table_for(0)
    assert t.reset_drone(0)["params_restored"] == []


def test_reset_evicts_attacker_from_the_telemetry_peer_set():
    """A peer that talked to the link once would otherwise keep receiving telemetry."""
    t = MavlinkTransport(_sim())
    t.peers.add(("10.10.30.66", 54321))
    t.peers.add(("172.30.10.10", 14550))

    out = t.reset_drone(0)

    assert out["peers_dropped"] == 2
    assert t.peers == set(), "attacker still subscribed after reset"


def test_reset_discards_a_partial_mission_upload():
    t = MavlinkTransport(_sim())
    t._mission_uploads[0] = {"count": 4, "items": []}

    out = t.reset_drone(0)

    assert out["mission_upload_discarded"] is True
    assert 0 not in t._mission_uploads


def test_reset_is_safe_on_a_clean_drone():
    t = MavlinkTransport(_sim())
    out = t.reset_drone(0)
    assert out == {"params_restored": [], "mission_upload_discarded": False, "peers_dropped": 0}
