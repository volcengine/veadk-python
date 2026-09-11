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

"""Small public profiles for people recorded on authorized Skill reviews."""

from collections import OrderedDict
from threading import Lock
from time import monotonic
from typing import Any, TypedDict
from urllib.parse import urlsplit

import volcenginesdkid as sdk

from frontend.server.user_management.directory import IdentityDirectory
from frontend.server.user_management.errors import UserManagementError


class ReviewerProfile(TypedDict):
    id: str
    name: str
    email: str
    avatarUrl: str


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _avatar_url(value: Any) -> str:
    url = _text(value)
    try:
        parsed = urlsplit(url)
        if (
            parsed.scheme in {"https", "http"}
            and parsed.hostname
            and not parsed.username
            and not parsed.password
        ):
            return url
    except ValueError:
        pass
    return ""


class ReviewerProfileResolver:
    """Resolve recorded pool UIDs, never search a user pool by display name.

    Call only after the review service has authorized access to the application
    and read its actor IDs from stored metadata, not from a browser lookup query
    The directory already owns provider-specific endpoints and rotating credentials
    Only public profile fields are cached; no roles or authentication data are kept
    """

    def __init__(self, directory: IdentityDirectory | None = None):
        self.directory = directory
        self._cache: OrderedDict[str, tuple[float, ReviewerProfile]] = OrderedDict()
        self._cache_lock = Lock()

    def resolve(
        self,
        *,
        identity_uid: str = "",
        owner_id: str = "",
        fallback_name: str = "",
    ) -> ReviewerProfile:
        uid = _text(identity_uid)
        fallback: ReviewerProfile = {
            "id": uid or _text(owner_id),
            "name": _text(fallback_name) or _text(owner_id) or uid,
            "email": "",
            "avatarUrl": "",
        }
        if not self.directory or not uid:
            return fallback
        with self._cache_lock:
            cached = self._cache.get(uid)
            if cached and cached[0] > monotonic():
                self._cache.move_to_end(uid)
                return {**cached[1], "name": cached[1]["name"] or fallback["name"]}
        try:
            # PoolUser intentionally omits profile fields; read the SDK response
            # through the same authenticated adapter without listing other users
            user = self.directory._call(
                "get_user",
                sdk.GetUserRequest(user_pool_uid=self.directory.pool_uid, user_uid=uid),
            )
        except UserManagementError:
            # Historical decisions stay readable if the user was deleted or the
            # profile service is temporarily unavailable
            return fallback
        if _text(getattr(user, "uid", "")) != uid:
            return fallback
        profile: ReviewerProfile = {
            "id": uid,
            "name": next(
                (
                    text
                    for key in ("name", "preferred_username", "nickname", "email")
                    if (text := _text(getattr(user, key, "")))
                ),
                "",
            ),
            "email": _text(getattr(user, "email", "")),
            "avatarUrl": _avatar_url(getattr(user, "picture", "")),
        }
        with self._cache_lock:
            self._cache[uid] = (monotonic() + 60, profile)
            self._cache.move_to_end(uid)
            while len(self._cache) > 128:
                self._cache.popitem(last=False)
        return {**profile, "name": profile["name"] or fallback["name"]}
