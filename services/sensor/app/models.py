from __future__ import annotations

from pydantic import BaseModel


class Alert(BaseModel):
    """Alert contract with the C2 (`IdsAlertIn`); keep field names/types in sync.

    {"ts":"<ISO8601>","signature":"<rule msg>","sid":<int>,"severity":<1-3>,
     "category":"<string>","src_ip":"<ip>","src_port":<int>,
     "dest_ip":"<ip>","dest_port":<int>,"proto":"<TCP|UDP>","iface":"<string>"}
    """

    ts: str
    signature: str
    sid: int
    severity: int
    category: str = ""
    src_ip: str
    src_port: int | None = None
    dest_ip: str
    dest_port: int | None = None
    proto: str
    iface: str = ""

    # Triggering bytes: base64 as Suricata emits it, plus its printable rendering.
    payload: str = ""
    payload_printable: str = ""


class Flow(BaseModel):
    """Normalized subset of a Suricata eve.json `flow` record."""

    ts: str
    src_ip: str
    src_port: int | None = None
    dest_ip: str
    dest_port: int | None = None
    proto: str
    iface: str = ""
    state: str = ""
    pkts_toserver: int = 0
    pkts_toclient: int = 0
    bytes_toserver: int = 0
    bytes_toclient: int = 0
    start: str = ""
    end: str = ""
