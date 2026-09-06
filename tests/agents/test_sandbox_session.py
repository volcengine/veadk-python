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


"""Control-plane pagination, rotation and ambiguous creation regression tests."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from veadk.agents import _sandbox_session as sessions


def info(sid="old", user="logical", seconds=3600, status="Ready"):
    return SimpleNamespace(
        session_id=sid,
        user_session_id=user,
        status=status,
        created_at="2026-09-06T00:00:00Z",
        expire_at=(datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat(),
    )


def test_reuses_lease_only_with_sufficient_lifetime():
    current = info()
    client = Mock()
    client.list_sessions.return_value = SimpleNamespace(
        session_infos=[current], next_token=None
    )
    result = sessions._get_or_create_agentkit_session(
        client=client,
        tool_id="tool",
        tool_user_session_id="logical",
        ttl=1800,
        min_remaining_seconds=900,
    )
    assert result is current
    client.create_session.assert_not_called()


def test_rotates_expiring_session_and_recovers_lost_create_response():
    old = info(seconds=5)
    rotated = sessions._rotated_user_session_id("logical", [old])
    created = info(sid="new", user=rotated, status="Starting")
    client = Mock()
    client.list_sessions.side_effect = [
        SimpleNamespace(session_infos=[old], next_token=None),
        SimpleNamespace(session_infos=[old, created], next_token=None),
    ]
    client.create_session.side_effect = TimeoutError("fixture")
    result = sessions._get_or_create_agentkit_session(
        client=client,
        tool_id="tool",
        tool_user_session_id="logical",
        ttl=1800,
        min_remaining_seconds=900,
    )
    assert result is created
    assert client.create_session.call_count == 1
    assert client.create_session.call_args.args[0].user_session_id == rotated


def test_list_failure_does_not_create_another_session():
    client = Mock()
    client.list_sessions.side_effect = TimeoutError("fixture")
    with pytest.raises(TimeoutError):
        sessions._get_or_create_agentkit_session(
            client=client, tool_id="tool", tool_user_session_id="logical", ttl=1800
        )
    client.create_session.assert_not_called()


def test_pagination_and_repeated_token_guard():
    client = Mock()
    client.list_sessions.side_effect = [
        SimpleNamespace(session_infos=[], next_token="next"),
        SimpleNamespace(session_infos=[info()], next_token=None),
    ]
    assert (
        len(
            sessions._list_agentkit_sessions(
                client=client, tool_id="tool", physical_user_session_id_base="logical"
            )
        )
        == 1
    )
    assert client.list_sessions.call_args.args[0].next_token == "next"
    client.list_sessions.side_effect = None
    client.list_sessions.return_value = SimpleNamespace(
        session_infos=[], next_token="repeat"
    )
    with pytest.raises(RuntimeError, match="repeated NextToken"):
        sessions._list_agentkit_sessions(
            client=client, tool_id="tool", physical_user_session_id_base="logical"
        )


def test_logical_id_encoding_is_stable_and_bounded():
    encoded = sessions._safe_agentkit_user_session_id("用户/" * 500)
    assert len(encoded) <= 185
    assert encoded == sessions._safe_agentkit_user_session_id("用户/" * 500)
    assert sessions._safe_agentkit_user_session_id(
        "a/b"
    ) != sessions._safe_agentkit_user_session_id("a_b")
