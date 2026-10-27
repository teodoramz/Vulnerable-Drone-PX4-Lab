from __future__ import annotations

import enum


class Role(str, enum.Enum):
    admin = "admin"
    operator = "operator"
    observer = "observer"


class Permission(str, enum.Enum):
    USER_MANAGE = "user:manage"
    DRONE_READ = "drone:read"
    DRONE_POWER = "drone:power"
    DRONE_CLAIM = "drone:claim"
    DRONE_COMMAND = "drone:command"
    DRONE_FORCE_RELEASE = "drone:force_release"
    MISSION_READ = "mission:read"
    MISSION_WRITE = "mission:write"
    AUDIT_READ = "audit:read"


# Permission matrix. Admin implicitly holds everything.
_ROLE_PERMISSIONS: dict[Role, set[Permission]] = {
    Role.admin: set(Permission),
    Role.operator: {
        Permission.DRONE_READ,
        Permission.DRONE_POWER,
        Permission.DRONE_CLAIM,
        Permission.DRONE_COMMAND,
        Permission.MISSION_READ,
        Permission.MISSION_WRITE,
        # Read-only history; USER_MANAGE stays admin-only.
        Permission.AUDIT_READ,
    },
    Role.observer: {
        Permission.DRONE_READ,
        Permission.MISSION_READ,
    },
}


def has_permission(role: Role, permission: Permission) -> bool:
    return permission in _ROLE_PERMISSIONS.get(role, set())
