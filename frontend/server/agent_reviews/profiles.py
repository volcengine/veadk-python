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

"""Resolve review actors through the deployment's existing Identity directory."""

from typing import Any
from urllib.parse import urlsplit

from frontend.server.user_management.errors import UserManagementError


def resolve_profile(directory: Any, person: dict[str, str]) -> dict[str, str]:
    uid = person.get("identityUid", "")
    if not directory:
        return person
    import volcenginesdkid as sdk

    try:
        if not uid:
            # Deployment tags contain the trusted subject, not necessarily GetUser's UID
            matches = [
                user.uid
                for user in directory.users()
                if person.get("id") in {user.subject, user.uid}
            ]
            if len(matches) != 1:
                return person
            uid = matches[0]
        user = directory._call(
            "get_user",
            sdk.GetUserRequest(user_pool_uid=directory.pool_uid, user_uid=uid),
        )
    except UserManagementError:
        # A removed directory user must not erase the persisted audit identity
        return person
    if str(getattr(user, "uid", "")) != uid:
        return person
    picture = str(getattr(user, "picture", "") or "")
    try:
        parsed = urlsplit(picture)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
        ):
            picture = ""
    except ValueError:
        picture = ""
    name = next(
        (
            str(getattr(user, key))
            for key in ("name", "preferred_username", "nickname", "email")
            if getattr(user, key, None)
        ),
        person["name"],
    )
    return {
        **person,
        "name": name,
        "email": str(getattr(user, "email", "") or ""),
        "avatarUrl": picture,
    }
