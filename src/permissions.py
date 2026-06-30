from __future__ import annotations
"""Local-only permission compatibility shim for v10."""
from dataclasses import dataclass
from typing import Set

LOCAL_PERMISSIONS = {"read_config", "write_config", "build_workbook", "download", "manage_secrets", "manage_clients", "manage_users", "view_dashboard", "refresh_prices", "view_audit"}

@dataclass(frozen=True)
class UserContext:
    user_id: str = "local"
    email: str = "local"
    role: str = "advisor"
    workspace_id: str = "local"
    @property
    def permissions(self) -> Set[str]:
        return set(LOCAL_PERMISSIONS)
    def can(self, permission: str) -> bool:
        return permission in LOCAL_PERMISSIONS

def user_from_headers(headers, default_role: str = "advisor", workspace_id: str = "local") -> UserContext:
    return UserContext(role=default_role or "advisor")

def require(user: UserContext, permission: str) -> None:
    if not user.can(permission):
        raise PermissionError(f"Permission denied: {permission}")
