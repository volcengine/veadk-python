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

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from frontend.server.skills.reviewer_profiles import ReviewerProfileResolver
from frontend.server.user_management.directory import IdentityDirectory
from frontend.server.user_management.errors import UserManagementError
from veadk.utils.cloud_provider import CloudProvider


def make_directory(provider: CloudProvider = "volcengine"):
    directory = IdentityDirectory(
        "pool-for-" + provider,
        provider,
        "cn-beijing" if provider == "volcengine" else "ap-southeast-1",
        lambda: ("unused", "unused", None),
    )
    return directory


@pytest.mark.parametrize("provider", ["volcengine", "byteplus"])
def test_fetches_only_known_reviewer_uid_and_returns_profile_fields(
    provider: CloudProvider,
):
    directory = make_directory(provider)
    directory._call = Mock(
        return_value=SimpleNamespace(
            uid="reviewer-uid",
            name="审批人",
            email="reviewer@example.com",
            picture="https://images.example.com/reviewer.png",
            user_metadata='{"secret": "must not be returned"}',
            group_uids=["private-role-group"],
        )
    )
    resolver = ReviewerProfileResolver(directory)

    result = resolver.resolve(
        identity_uid="reviewer-uid", owner_id="oidc|reviewer", fallback_name="旧名字"
    )

    assert result == {
        "id": "reviewer-uid",
        "name": "审批人",
        "email": "reviewer@example.com",
        "avatarUrl": "https://images.example.com/reviewer.png",
    }
    directory._call.assert_called_once()
    action, request = directory._call.call_args.args
    assert action == "get_user"
    assert request.user_pool_uid == "pool-for-" + provider
    assert request.user_uid == "reviewer-uid"


def test_local_identity_does_not_try_name_or_subject_lookup():
    directory = make_directory()
    directory._call = Mock(side_effect=AssertionError("Unexpected Identity request"))

    assert ReviewerProfileResolver(directory).resolve(
        owner_id="test", fallback_name="本地管理员"
    ) == {
        "id": "test",
        "name": "本地管理员",
        "email": "",
        "avatarUrl": "",
    }
    directory._call.assert_not_called()


def test_no_directory_preserves_recorded_name_for_browser_initial_avatar():
    assert ReviewerProfileResolver().resolve(
        identity_uid="reviewer-uid", fallback_name="审批人"
    ) == {"id": "reviewer-uid", "name": "审批人", "email": "", "avatarUrl": ""}


@pytest.mark.parametrize("status", [404, 503])
def test_deleted_user_or_identity_outage_does_not_break_review_history(status):
    directory = make_directory()
    directory._call = Mock(side_effect=UserManagementError(status, "unavailable"))

    assert ReviewerProfileResolver(directory).resolve(
        identity_uid="reviewer-uid", fallback_name="记录里的审批人"
    ) == {
        "id": "reviewer-uid",
        "name": "记录里的审批人",
        "email": "",
        "avatarUrl": "",
    }


def test_mismatched_uid_does_not_expose_another_users_profile():
    directory = make_directory()
    directory._call = Mock(
        return_value=SimpleNamespace(uid="another-user", name="另一人", email="hidden")
    )
    result = ReviewerProfileResolver(directory).resolve(
        identity_uid="reviewer-uid", fallback_name="审批人"
    )
    assert result["name"] == "审批人"
    assert result["email"] == ""


@pytest.mark.parametrize(
    "picture",
    [
        "javascript:alert(1)",
        "data:image/svg+xml,<svg/>",
        "//example.com/a.png",
        "https://user:password@example.com/a.png",
    ],
)
def test_rejects_unsafe_avatar_urls(picture):
    directory = make_directory()
    directory._call = Mock(
        return_value=SimpleNamespace(uid="reviewer-uid", name="审批人", picture=picture)
    )
    result = ReviewerProfileResolver(directory).resolve(identity_uid="reviewer-uid")
    assert result["avatarUrl"] == ""


def test_repeated_reviewer_lookup_uses_profile_cache_and_returns_copy():
    directory = make_directory()
    directory._call = Mock(
        return_value=SimpleNamespace(uid="reviewer-uid", name="审批人")
    )
    resolver = ReviewerProfileResolver(directory)
    first = resolver.resolve(identity_uid="reviewer-uid")
    first["name"] = "must not mutate cache"

    assert resolver.resolve(identity_uid="reviewer-uid")["name"] == "审批人"
    directory._call.assert_called_once()


def test_profile_cache_expires_and_refreshes_name(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(
        "frontend.server.skills.reviewer_profiles.monotonic", lambda: now[0]
    )
    directory = make_directory()
    directory._call = Mock(
        side_effect=[
            SimpleNamespace(uid="reviewer-uid", name="旧名字"),
            SimpleNamespace(uid="reviewer-uid", name="新名字"),
        ]
    )
    resolver = ReviewerProfileResolver(directory)
    assert resolver.resolve(identity_uid="reviewer-uid")["name"] == "旧名字"
    now[0] += 61
    assert resolver.resolve(identity_uid="reviewer-uid")["name"] == "新名字"


def test_missing_name_uses_recorded_name_instead_of_another_identity():
    directory = make_directory()
    directory._call = Mock(return_value=SimpleNamespace(uid="reviewer-uid"))
    resolver = ReviewerProfileResolver(directory)
    assert (
        resolver.resolve(identity_uid="reviewer-uid", fallback_name="原审批人")["name"]
        == "原审批人"
    )
