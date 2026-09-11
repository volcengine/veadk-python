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

"""Small Identity control-plane adapter shared by both cloud providers."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import volcenginesdkcore
import volcenginesdkid as sdk
from urllib3.exceptions import HTTPError
from volcenginesdkcore.rest import ApiException

from veadk.utils.cloud_provider import (
    CloudProvider,
    configure_openapi_tls,
    identity_openapi_host,
)

from .errors import UserManagementError


@dataclass(frozen=True)
class PoolUser:
    uid: str
    subject: str
    email: str
    name: str
    status: str
    groups: tuple[str, ...] = ()
    last_login: str = ""
    username: str = ""

    @classmethod
    def from_sdk(cls, value: Any) -> "PoolUser":
        return cls(
            uid=value.uid,
            subject=value.sub or "",
            email=value.email or "",
            name=value.name
            or value.preferred_username
            or value.nickname
            or value.email
            or value.uid,
            status=value.user_state or "",
            groups=tuple(value.group_uids or []),
            last_login=value.latest_login or "",
            username=value.preferred_username or "",
        )


@dataclass(frozen=True)
class IdentityGroup:
    uid: str
    name: str
    description: str


class IdentityDirectory:
    def __init__(
        self,
        pool_uid: str,
        provider: CloudProvider,
        region: str,
        credentials: Callable[[], tuple[str, str, str | None]],
    ):
        self.pool_uid = pool_uid
        self.provider: CloudProvider = provider
        self.region = region
        self.credentials = credentials

    def _call(self, action: str, body: Any) -> Any:
        # Resolve credentials for each call so rotating cloud credentials remain valid
        ak, sk, token = self.credentials()
        # The generated SDK types host as None although it accepts URL strings
        config: Any = volcenginesdkcore.Configuration()
        config.ak, config.sk, config.session_token = ak, sk, token or ""
        config.region = self.region
        config.host = f"https://{identity_openapi_host(self.region, self.provider)}"
        config.logger = {}
        configure_openapi_tls(config)
        client = sdk.IDApi(volcenginesdkcore.ApiClient(config))
        try:
            return getattr(client, action)(body, _request_timeout=(5, 15))
        except ApiException as error:
            if error.status == 404:
                raise UserManagementError(404, "identity_resource_missing") from error
            raise UserManagementError(503, "identity_unavailable") from error
        except (HTTPError, TimeoutError) as error:
            raise UserManagementError(503, "identity_unavailable") from error

    def users(self) -> list[PoolUser]:
        users: list[PoolUser] = []
        page = 1
        while True:
            response = self._call(
                "list_users",
                sdk.ListUsersRequest(
                    user_pool_uid=self.pool_uid,
                    page_number=page,
                    page_size=100,
                ),
            )
            batch = response.data or []
            users.extend(PoolUser.from_sdk(user) for user in batch)
            if not batch or len(users) >= response.total_count:
                return users
            page += 1

    def user(self, uid: str) -> PoolUser:
        return PoolUser.from_sdk(
            self._call(
                "get_user",
                sdk.GetUserRequest(
                    user_pool_uid=self.pool_uid,
                    user_uid=uid,
                ),
            )
        )

    def groups(self) -> list[IdentityGroup]:
        groups: list[IdentityGroup] = []
        page = 1
        while True:
            response = self._call(
                "list_groups",
                sdk.ListGroupsRequest(
                    user_pool_uid=self.pool_uid,
                    page_number=page,
                    page_size=100,
                ),
            )
            batch = response.data or []
            groups.extend(
                IdentityGroup(group.uid, group.name, group.description or "")
                for group in batch
            )
            if not batch or len(groups) >= response.total_count:
                return groups
            page += 1

    def create_group(self, name: str, description: str) -> IdentityGroup:
        result = self._call(
            "create_group",
            sdk.CreateGroupRequest(
                user_pool_uid=self.pool_uid,
                name=name,
                description=description,
            ),
        )
        return IdentityGroup(result.uid, name, description)

    def describe_group(self, uid: str, description: str) -> None:
        self._call(
            "update_group",
            sdk.UpdateGroupRequest(
                user_pool_uid=self.pool_uid,
                group_uid=uid,
                description=description,
            ),
        )

    def add(self, group_uid: str, user_uid: str) -> None:
        self._call(
            "add_users_to_group",
            sdk.AddUsersToGroupRequest(
                user_pool_uid=self.pool_uid,
                group_uid=group_uid,
                user_uids=[user_uid],
            ),
        )

    def remove(self, group_uid: str, user_uid: str) -> None:
        self._call(
            "remove_users_from_group",
            sdk.RemoveUsersFromGroupRequest(
                user_pool_uid=self.pool_uid,
                group_uid=group_uid,
                user_uids=[user_uid],
            ),
        )
