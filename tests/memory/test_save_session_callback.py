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

"""Unit tests for ``veadk.memory.save_session_callback``.

These exercise the throttling / session-switch logic of
``save_session_to_long_term_memory`` against a fully mocked callback context.
No real session service or long-term memory backend is used.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from veadk.memory import save_session_callback as ssc
from veadk.memory.save_session_callback import save_session_to_long_term_memory


@pytest.fixture(autouse=True)
def _clear_caches():
    """Module-level caches persist across calls; reset them per test."""
    ssc._session_save_cache.clear()
    ssc._active_sessions.clear()
    yield
    ssc._session_save_cache.clear()
    ssc._active_sessions.clear()


def _make_session(session_id: str, event_count: int = 0) -> MagicMock:
    session = MagicMock()
    session.id = session_id
    session.events = [MagicMock() for _ in range(event_count)]
    return session


def _make_context(
    *,
    app_name: str = "app",
    user_id: str = "user",
    session_id: str = "session",
    long_term_memory: object | None = None,
    sessions: dict | None = None,
) -> MagicMock:
    """Build a mock CallbackContext.

    ``sessions`` maps session_id -> session object returned by
    ``session_service.get_session``.
    """
    ctx = MagicMock()
    inv = ctx._invocation_context
    inv.app_name = app_name
    inv.user_id = user_id
    inv.agent.long_term_memory = long_term_memory
    inv.session.id = session_id

    store = sessions if sessions is not None else {}

    async def get_session(app_name, user_id, session_id):
        return store.get(session_id)

    inv.session_service.get_session = AsyncMock(side_effect=get_session)
    return ctx


@pytest.mark.asyncio
async def test_returns_none_when_no_long_term_memory():
    ctx = _make_context(long_term_memory=None)
    result = await save_session_to_long_term_memory(ctx)
    assert result is None
    # No session lookup should have happened.
    ctx._invocation_context.session_service.get_session.assert_not_called()


@pytest.mark.asyncio
async def test_first_save_adds_session_and_populates_cache():
    ltm = MagicMock()
    ltm.add_session_to_memory = AsyncMock()
    session = _make_session("session", event_count=3)
    ctx = _make_context(long_term_memory=ltm, sessions={"session": session})

    await save_session_to_long_term_memory(ctx)

    ltm.add_session_to_memory.assert_awaited_once_with(session)
    cache_key = ("app", "user", "session")
    assert cache_key in ssc._session_save_cache
    assert ssc._session_save_cache[cache_key]["last_event_count"] == 3
    assert ssc._active_sessions[("app", "user")] == "session"


@pytest.mark.asyncio
async def test_skip_save_when_below_thresholds(monkeypatch):
    """A recent save with too few new events must be skipped."""
    monkeypatch.setattr(ssc, "MIN_MESSAGES_THRESHOLD", 10)
    monkeypatch.setattr(ssc, "MIN_TIME_THRESHOLD", 60)

    ltm = MagicMock()
    ltm.add_session_to_memory = AsyncMock()
    session = _make_session("session", event_count=2)
    ctx = _make_context(long_term_memory=ltm, sessions={"session": session})

    # Seed cache as if a save just happened with the same event count.
    import time

    ssc._session_save_cache[("app", "user", "session")] = {
        "last_save_time": time.time(),
        "last_event_count": 1,
    }

    result = await save_session_to_long_term_memory(ctx)
    assert result is None
    ltm.add_session_to_memory.assert_not_called()


@pytest.mark.asyncio
async def test_save_when_enough_new_events(monkeypatch):
    monkeypatch.setattr(ssc, "MIN_MESSAGES_THRESHOLD", 10)
    monkeypatch.setattr(ssc, "MIN_TIME_THRESHOLD", 60)

    ltm = MagicMock()
    ltm.add_session_to_memory = AsyncMock()
    session = _make_session("session", event_count=20)
    ctx = _make_context(long_term_memory=ltm, sessions={"session": session})

    import time

    ssc._session_save_cache[("app", "user", "session")] = {
        "last_save_time": time.time(),
        "last_event_count": 1,
    }

    await save_session_to_long_term_memory(ctx)
    ltm.add_session_to_memory.assert_awaited_once_with(session)
    assert ssc._session_save_cache[("app", "user", "session")]["last_event_count"] == 20


@pytest.mark.asyncio
async def test_session_switch_force_saves_previous(monkeypatch):
    monkeypatch.setattr(ssc, "MIN_MESSAGES_THRESHOLD", 10)
    monkeypatch.setattr(ssc, "MIN_TIME_THRESHOLD", 60)

    ltm = MagicMock()
    ltm.add_session_to_memory = AsyncMock()

    old_session = _make_session("old", event_count=5)
    new_session = _make_session("new", event_count=1)

    ctx = _make_context(
        session_id="new",
        long_term_memory=ltm,
        sessions={"old": old_session, "new": new_session},
    )

    # Mark "old" as the previously active session for this user.
    ssc._active_sessions[("app", "user")] = "old"

    await save_session_to_long_term_memory(ctx)

    # The previous session must be force-saved, and the active session updated.
    saved = [call.args[0] for call in ltm.add_session_to_memory.await_args_list]
    assert old_session in saved
    assert ssc._active_sessions[("app", "user")] == "new"
    assert ("app", "user", "old") in ssc._session_save_cache


@pytest.mark.asyncio
async def test_returns_none_when_session_not_found():
    ltm = MagicMock()
    ltm.add_session_to_memory = AsyncMock()
    ctx = _make_context(long_term_memory=ltm, sessions={})  # get_session -> None

    result = await save_session_to_long_term_memory(ctx)
    assert result is None
    ltm.add_session_to_memory.assert_not_called()


@pytest.mark.asyncio
async def test_attribute_error_is_swallowed():
    """A malformed context raising AttributeError must not propagate."""
    ctx = MagicMock()
    # Accessing the agent attribute raises -> caught by the handler.
    type(ctx._invocation_context).agent = property(
        lambda self: (_ for _ in ()).throw(AttributeError("boom"))
    )
    result = await save_session_to_long_term_memory(ctx)
    assert result is None
