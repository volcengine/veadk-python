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

"""Studio roles stored exclusively in application-scoped Identity groups."""

import json
import logging
from dataclasses import replace
from threading import RLock
from uuid import uuid4

from .directory import IdentityDirectory, IdentityGroup, PoolUser
from .errors import UserManagementError
from .policy import StudioPrincipal, StudioRole, parse_role_members

logger = logging.getLogger(__name__)


class UserManagementService:
    def __init__(
        self,
        directory: IdentityDirectory,
        pool_uid: str,
        client_uid: str,
        provider: str,
    ):
        self.directory = directory
        self.pool_uid = pool_uid
        self.client_uid = client_uid
        self.provider = provider
        self.role_groups: dict[StudioRole, IdentityGroup] = {}
        self.protected_user_uid = ""
        self.default_role = StudioRole.USER
        # Only the immutable subject-to-UID mapping is cached, never permissions
        self._subject_uids: dict[str, str] = {}
        self._write_lock = RLock()

    def initialize(
        self,
        bootstrap: str = "",
        admins: str = "",
        developers: str = "",
        *,
        allow_initialize: bool = False,
    ) -> None:
        bootstrap = bootstrap.strip()
        names = {
            role: f"studio-{self.client_uid}-{role.value.replace('_', '-')}"
            for role in StudioRole
        }
        existing = self.directory.groups()
        role_groups: dict[StudioRole, IdentityGroup] = {}
        for role, name in names.items():
            matches = [group for group in existing if group.name == name]
            if len(matches) > 1:
                raise UserManagementError(503, "duplicate_role_groups")
            if matches:
                role_groups[role] = matches[0]
        self.role_groups = role_groups
        admin_group = self.role_groups.get(StudioRole.SUPER_ADMIN)
        try:
            metadata = json.loads(admin_group.description) if admin_group else {}
        except json.JSONDecodeError:
            metadata = {}
        if not isinstance(metadata, dict):
            metadata = {}
        self.protected_user_uid = str(metadata.get("protectedUserUid") or "")
        initialized = metadata.get("initialized") is True
        if initialized:
            if len(self.role_groups) != len(StudioRole):
                raise UserManagementError(503, "roles_not_initialized")
            default_role = metadata.get("defaultRole", StudioRole.USER.value)
            if default_role not in (StudioRole.ADMIN.value, StudioRole.USER.value):
                raise UserManagementError(503, "invalid_default_role")
            self.default_role = StudioRole(default_role)
            if self.protected_user_uid:
                protected = self.directory.user(self.protected_user_uid)
                if self._role(protected) != StudioRole.SUPER_ADMIN:
                    raise UserManagementError(503, "protected_administrator_missing")
                return
            if not bootstrap:
                return
        elif not bootstrap and not allow_initialize:
            raise UserManagementError(503, "roles_not_initialized")

        users = self.directory.users()
        owner = None
        if bootstrap:
            matches = [
                user
                for user in users
                if user.uid == bootstrap
                or user.email.casefold() == bootstrap.casefold()
            ]
            if len(matches) != 1:
                raise UserManagementError(400, "bootstrap_user_not_unique")
            owner = matches[0]
        if initialized and owner is not None:
            # Explicitly add the first super admin without resetting existing roles
            self._set_role(owner, StudioRole.SUPER_ADMIN)
            self.protected_user_uid = owner.uid
            self._save_metadata()
            return
        admin_members, developer_members = (
            parse_role_members(admins),
            parse_role_members(developers),
        )
        # Validate the whole migration before creating groups or assigning roles
        user_identifiers = {
            user.uid: {
                value.casefold()
                for value in (user.uid, user.subject, user.email, user.username)
                if value
            }
            for user in users
        }
        for identifier in admin_members | developer_members:
            if sum(identifier in values for values in user_identifiers.values()) != 1:
                raise UserManagementError(400, "legacy_role_member_not_unique")
        for role, name in names.items():
            if role not in self.role_groups:
                self.role_groups[role] = self.directory.create_group(
                    name, "Studio application role"
                )
        for user in users:
            identifiers = user_identifiers[user.uid]
            if owner and user.uid == owner.uid:
                self._set_role(user, StudioRole.SUPER_ADMIN)
            elif identifiers & admin_members:
                self._set_role(user, StudioRole.ADMIN)
            elif identifiers & developer_members:
                self._set_role(user, StudioRole.DEVELOPER)
        self.default_role = (
            StudioRole.USER
            if owner or admin_members or developer_members
            else StudioRole.ADMIN
        )
        self.protected_user_uid = owner.uid if owner else ""
        self._save_metadata()
        logger.info(
            "Studio Identity roles initialized: pool=%s client=%s default_role=%s",
            self.pool_uid,
            self.client_uid,
            self.default_role,
        )

    def _save_metadata(self) -> None:
        self.directory.describe_group(
            self.role_groups[StudioRole.SUPER_ADMIN].uid,
            json.dumps(
                {
                    "application": "studio",
                    "clientUid": self.client_uid,
                    "protectedUserUid": self.protected_user_uid,
                    "initialized": True,
                    "defaultRole": self.default_role.value,
                }
            ),
        )

    def _role(self, user: PoolUser) -> StudioRole:
        roles = [
            role for role, group in self.role_groups.items() if group.uid in user.groups
        ]
        # Concurrent or interrupted membership updates never accumulate privileges
        if not roles:
            return self.default_role
        return roles[0] if len(roles) == 1 else StudioRole.USER

    def _resolve_user(self, principal: StudioPrincipal | None) -> PoolUser:
        if principal is None:
            raise UserManagementError(401, "sign_in_required")
        subject = principal.owner_id
        uid = self._subject_uids.get(subject)
        if not uid:
            matches = [
                user
                for user in self.directory.users()
                if subject in (user.subject, user.uid)
            ]
            if len(matches) != 1:
                raise UserManagementError(403, "user_not_in_pool")
            uid = matches[0].uid
            self._subject_uids[subject] = uid
        user = self.directory.user(uid)
        if subject not in (user.subject, user.uid):
            self._subject_uids.pop(subject, None)
            raise UserManagementError(403, "user_not_in_pool")
        if user.status.upper() in {
            "DISABLED",
            "FORBIDDEN",
            "LOCKED",
            "DELETED",
            "SUSPENDED",
        }:
            raise UserManagementError(403, "user_disabled")
        return user

    def principal_for(self, principal: StudioPrincipal) -> StudioPrincipal:
        user = self._resolve_user(principal)
        return replace(principal, role=self._role(user), identity_uid=user.uid)

    def _require_super_admin(self, actor: StudioPrincipal | None) -> PoolUser:
        user = self._resolve_user(actor)
        if self._role(user) != StudioRole.SUPER_ADMIN:
            raise UserManagementError(403, "super_administrator_required")
        return user

    def _payload(self, user: PoolUser, actor_uid: str) -> dict:
        roles = [
            role for role, group in self.role_groups.items() if group.uid in user.groups
        ]
        return {
            "id": user.uid,
            "name": user.name,
            "email": user.email,
            "role": self._role(user).value,
            "status": user.status,
            "lastLogin": user.last_login,
            "protected": user.uid == self.protected_user_uid,
            "currentUser": user.uid == actor_uid,
            "roleConflict": len(roles) > 1,
        }

    def list_users(
        self,
        actor: StudioPrincipal | None,
        page: int = 1,
        page_size: int = 20,
        query: str = "",
        role: StudioRole | None = None,
    ) -> dict:
        actor_user = self._require_super_admin(actor)
        users = self.directory.users()
        needle = query.strip().casefold()
        filtered = [
            user
            for user in users
            if (
                (
                    not needle
                    or needle in f"{user.name} {user.email} {user.uid}".casefold()
                )
                and (role is None or self._role(user) == role)
            )
        ]
        filtered.sort(
            key=lambda user: (
                user.uid != self.protected_user_uid,
                user.name.casefold(),
                user.uid,
            )
        )
        start = (page - 1) * page_size
        return {
            "items": [
                self._payload(user, actor_user.uid)
                for user in filtered[start : start + page_size]
            ],
            "total": len(filtered),
            "poolTotal": len(users),
            "page": page,
            "pageSize": page_size,
            "userPoolId": self.pool_uid,
            "clientId": self.client_uid,
            "provider": self.provider,
        }

    def _set_role(self, user: PoolUser, role: StudioRole) -> PoolUser:
        group = self.role_groups[role]
        # Add first: a partially completed change resolves to the least privileged role
        if group.uid not in user.groups:
            self.directory.add(group.uid, user.uid)
        for old_group in self.role_groups.values():
            if old_group.uid != group.uid and old_group.uid in user.groups:
                self.directory.remove(old_group.uid, user.uid)
        updated = self.directory.user(user.uid)
        actual_groups = {group.uid for group in self.role_groups.values()} & set(
            updated.groups
        )
        if actual_groups != {group.uid}:
            raise UserManagementError(409, "role_change_conflict")
        return updated

    def change_role(
        self,
        actor: StudioPrincipal | None,
        user_uid: str,
        role: StudioRole,
        expected_role: StudioRole,
    ) -> dict:
        with self._write_lock:
            self.initialize()
            actor_user = self._require_super_admin(actor)
            user = self.directory.user(user_uid)
            if user.uid == self.protected_user_uid and role != StudioRole.SUPER_ADMIN:
                raise UserManagementError(409, "protected_administrator")
            if user.uid == actor_user.uid and role != StudioRole.SUPER_ADMIN:
                raise UserManagementError(409, "cannot_demote_self")
            current = self._role(user)
            if current != expected_role:
                raise UserManagementError(409, "role_change_conflict")
            operation_id = str(uuid4())
            logger.info(
                "Studio role change requested: operation=%s actor=%s target=%s from=%s to=%s pool=%s client=%s",
                operation_id,
                actor_user.uid,
                user.uid,
                current,
                role,
                self.pool_uid,
                self.client_uid,
            )
            updated = self._set_role(user, role)
            logger.info("Studio role change completed: operation=%s", operation_id)
            return {
                "user": self._payload(updated, actor_user.uid),
                "operationId": operation_id,
            }
