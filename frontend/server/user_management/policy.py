# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Role and ownership policy for AgentKit Studio."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any


class StudioRole(str, Enum):
    """Roles exposed by Studio's access endpoint."""

    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    DEVELOPER = "developer"
    USER = "user"

    def __str__(self) -> str:
        """Return the wire-format role name."""
        return self.value

    @property
    def is_admin(self) -> bool:
        return self in (StudioRole.ADMIN, StudioRole.SUPER_ADMIN)


def parse_role_members(value: str | None) -> frozenset[str]:
    """Parse a case-insensitive comma-separated role member list."""
    if not value:
        return frozenset()
    return frozenset(
        item.strip().casefold() for item in value.split(",") if item.strip()
    )


@dataclass(frozen=True)
class StudioPrincipal:
    """A trusted Studio identity and all names that may identify it."""

    owner_id: str
    display_name: str
    identifiers: frozenset[str]
    role: StudioRole | None = None
    identity_uid: str = ""

    @classmethod
    def from_claims(cls, claims: Mapping[str, Any]) -> StudioPrincipal | None:
        """Build a principal from validated OAuth or gateway claims."""
        values = {
            key: str(claims.get(key) or "").strip()
            for key in (
                "sub",
                "user_id",
                "uid",
                "email",
                "preferred_username",
                "username",
                "login",
                "name",
            )
        }
        owner_id = next(
            (
                values[key]
                for key in (
                    "sub",
                    "user_id",
                    "uid",
                    "email",
                    "preferred_username",
                    "username",
                    "login",
                )
                if values[key]
            ),
            "",
        )
        if not owner_id:
            return None
        display_name = next(
            (
                values[key]
                for key in (
                    "email",
                    "preferred_username",
                    "username",
                    "login",
                    "name",
                )
                if values[key]
            ),
            owner_id,
        )
        identifiers = frozenset(
            values[key].casefold()
            for key in (
                "sub",
                "user_id",
                "uid",
                "email",
                "preferred_username",
                "username",
                "login",
            )
            if values[key]
        )
        return cls(
            owner_id=owner_id,
            display_name=display_name,
            identifiers=identifiers,
        )

    @classmethod
    def local(cls, username: str) -> StudioPrincipal | None:
        """Build the convenience identity used by an unauthenticated local UI."""
        username = username.strip()
        if not username:
            return None
        return cls(
            owner_id=username,
            display_name=username,
            identifiers=frozenset({username.casefold()}),
        )


@dataclass(frozen=True)
class StudioAccessPolicy:
    """Resolve Studio roles and capabilities from configured member lists."""

    admins: frozenset[str]
    developers: frozenset[str]
    identity_roles: bool = False

    @classmethod
    def from_csv(
        cls,
        admins: str | None,
        developers: str | None,
        *,
        identity_roles: bool = False,
    ) -> StudioAccessPolicy:
        return cls(
            admins=parse_role_members(admins),
            developers=parse_role_members(developers),
            identity_roles=identity_roles,
        )

    @property
    def enabled(self) -> bool:
        """Whether explicit role enforcement is enabled."""
        return self.identity_roles or bool(self.admins or self.developers)

    def role_for(self, principal: StudioPrincipal | None) -> StudioRole:
        """Return a role, giving admin membership precedence."""
        if self.identity_roles:
            return principal.role if principal and principal.role else StudioRole.USER
        if not self.enabled:
            return StudioRole.ADMIN
        identifiers = principal.identifiers if principal else frozenset()
        if identifiers & self.admins:
            return StudioRole.ADMIN
        if identifiers & self.developers:
            return StudioRole.DEVELOPER
        return StudioRole.USER

    def access_payload(self, principal: StudioPrincipal | None) -> dict[str, Any]:
        """Return the frontend-facing access description."""
        role = self.role_for(principal)
        can_manage = role.is_admin or role == StudioRole.DEVELOPER
        return {
            "role": role.value,
            "username": principal.display_name if principal else "",
            "rbacEnabled": self.enabled,
            "capabilities": {
                "createAgents": can_manage,
                "createPersonalAgents": principal is not None or not self.enabled,
                "manageAgents": can_manage,
                "runtimeScope": "all" if role.is_admin else "mine",
                **(
                    {"manageUsers": role == StudioRole.SUPER_ADMIN}
                    if self.identity_roles
                    else {}
                ),
            },
        }


def runtime_belongs_to(
    tags: Mapping[str, str],
    principal: StudioPrincipal | None,
) -> bool:
    """Return whether runtime ownership tags identify ``principal``."""
    if principal is None:
        return False
    owner = str(tags.get("veadk:owner") or "").strip().casefold()
    return bool(owner and owner in principal.identifiers)


def runtime_attribution(
    principal: StudioPrincipal | None,
) -> tuple[str, str]:
    """Return truthful Runtime author and stable owner tag values."""
    if principal is not None:
        return (
            (principal.display_name or principal.owner_id).strip(),
            principal.owner_id.strip(),
        )
    return "", ""
