"""Stub PX4 parameter table for the mock MAVLink surface.

Not wired to the simulation: values are stored and round-tripped through
PARAM_REQUEST_LIST / PARAM_SET / PARAM_VALUE but change nothing. Parameter
attacks only have real effect on the px4 backend.
"""
from __future__ import annotations

# name -> default value (all reported as MAV_PARAM_TYPE_REAL32)
DEFAULT_PARAMS: dict[str, float] = {
    "MPC_XY_VEL_MAX": 8.0,
    "MPC_Z_VEL_MAX_UP": 3.0,
    "MPC_Z_VEL_MAX_DN": 1.0,
    "COM_DISARM_LAND": 2.0,
    "COM_RC_LOSS_T": 0.5,
    "NAV_DLL_ACT": 0.0,
    "NAV_RCL_ACT": 0.0,
    "MIS_TAKEOFF_ALT": 2.5,
    "RTL_RETURN_ALT": 30.0,
    "RTL_DESCEND_ALT": 10.0,
    "SYS_AUTOSTART": 10040.0,
}
