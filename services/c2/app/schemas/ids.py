from __future__ import annotations

from pydantic import BaseModel, Field


class IdsAlertIn(BaseModel):
    """Alert payload pushed by the sensor (Suricata sidecar).

    This shape is a fixed contract shared with the `sensor` service - do not
    change field names/types here without updating the sensor agent too.
    """

    ts: str
    signature: str
    sid: int
    severity: int = Field(ge=1, le=3)
    src_ip: str
    dest_ip: str
    proto: str

    # Optional: Suricata emits port-less alerts (ICMP etc.); never 422 a detection.
    category: str = ""
    src_port: int | None = None
    dest_port: int | None = None
    iface: str = ""
    # Triggering packet bytes (base64 + printable), if Suricata carries them.
    payload: str = ""
    payload_printable: str = ""


class IdsAlertOut(IdsAlertIn):
    """Same shape, returned to operators/blue-team clients."""
