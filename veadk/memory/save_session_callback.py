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

import time
from functools import lru_cache

from google.adk.agents.callback_context import CallbackContext
from google.adk.events import Event

from veadk.config import getenv
from veadk.extensions.decisions import (
    DEFAULT_JUDGEMENT_THRESHOLD,
    DecisionModelError,
    probability_threshold,
)
from veadk.memory.auto_save_judge import (
    DecisionMemorySaveJudge,
    build_memory_save_judge,
    events_text,
)
from veadk.utils.logger import get_logger

logger = get_logger(__name__)


# Session-level cache for tracking save state
# Format: {(app_name, user_id, session_id): {'last_save_time': float, 'last_event_count': int}}
_session_save_cache: dict = {}

# Track active session per user to detect session switches
# Format: {(app_name, user_id): session_id}
_active_sessions: dict = {}

# Configurable thresholds
MIN_MESSAGES_THRESHOLD = getenv(
    "MIN_MESSAGES_THRESHOLD", 10
)  # Minimum number of new messages before saving
MIN_TIME_THRESHOLD = getenv(
    "MIN_TIME_THRESHOLD", 60
)  # Minimum seconds between saves (1 minute)

# ``decision`` lets the configured decision model decide whether a turn is
# worth remembering; ``threshold`` keeps the two thresholds above.
MEMORY_SAVE_STRATEGY = getenv("MEMORY_SAVE_STRATEGY", "threshold")
# 阈值必须是 [0, 1] 的概率：越界的值会被夹紧，NaN / 非数字回落到默认值。
# 空字符串同样按"未配置"处理，避免 import 期直接抛错。
MEMORY_SAVE_WORTH_THRESHOLD = probability_threshold(
    getenv(
        "MEMORY_SAVE_WORTH_THRESHOLD",
        DEFAULT_JUDGEMENT_THRESHOLD,
        allow_false_values=True,
    ),
    name="MEMORY_SAVE_WORTH_THRESHOLD",
)


def _copy_session_with_events(session, events):
    return session.model_copy(update={"events": events})


@lru_cache(maxsize=1)
def _memory_save_judge() -> DecisionMemorySaveJudge | None:
    """Return the judge the configured strategy asks for, built once."""
    return build_memory_save_judge(MEMORY_SAVE_STRATEGY)


async def _should_persist(*, events: list[Event], throttled: bool) -> bool:
    """Decide whether new events are worth writing to long-term memory.

    The thresholds are the default. Under the ``decision`` strategy the
    judgement decides instead, so a turn that stated something durable is
    stored before it crosses the thresholds, and a trivial turn is not stored
    merely because it did. A failing judgement falls back to the thresholds.

    Args:
        events: The new events of the current session.
        throttled: Whether the thresholds would skip this save.

    Returns:
        Whether the events should be written to long-term memory.
    """
    judge = _memory_save_judge()
    if judge is None:
        return not throttled
    try:
        probability = await judge.aworth_saving(events_text=events_text(events))
    except DecisionModelError as exc:
        logger.warning(
            "memory save judge unavailable, using the save thresholds: %s", exc
        )
        return not throttled
    if probability >= MEMORY_SAVE_WORTH_THRESHOLD:
        return True
    logger.info(
        f"Skipping save: judgement {probability:.2f} is below "
        f"{MEMORY_SAVE_WORTH_THRESHOLD}."
    )
    return False


async def save_session_to_long_term_memory(
    callback_context: CallbackContext,
) -> None:
    """Save the current session to long-term memory.

    Args:
        callback_context: The callback context containing invocation information.

    Returns:
        None
    """
    try:
        agent = callback_context._invocation_context.agent

        long_term_memory = getattr(agent, "long_term_memory", None)
        if not long_term_memory:
            logger.error(
                "Long-term memory is not initialized in agent, cannot save session to memory."
            )
            return None
        auto_save_memory_policy = getattr(agent, "auto_save_memory_policy", "default")

        app_name = callback_context._invocation_context.app_name
        user_id = callback_context._invocation_context.user_id
        session_id = callback_context._invocation_context.session.id
        session_service = callback_context._invocation_context.session_service

        current_time = time.time()

        # Detect session switch and force save previous session
        user_key = (app_name, user_id)
        previous_session_id = _active_sessions.get(user_key)

        if previous_session_id and previous_session_id != session_id:
            logger.info(
                f"Session switch detected for user {user_id}: "
                f"{previous_session_id} -> {session_id}. "
                f"Force saving previous session."
            )
            old_session = await session_service.get_session(
                app_name=app_name,
                user_id=user_id,
                session_id=previous_session_id,
            )
            if old_session:
                old_cache_key = (app_name, user_id, previous_session_id)
                old_cache_info = _session_save_cache.get(old_cache_key, {})
                old_last_event_count = old_cache_info.get("last_event_count", 0)
                old_events = getattr(old_session, "events", [])
                old_event_count = len(old_events)

                if old_last_event_count > old_event_count:
                    logger.warning(
                        f"Saved event cursor for previous session `{old_session.id}` "
                        f"({old_last_event_count}) is greater than current event count "
                        f"({old_event_count}); resetting cursor to 0."
                    )
                    old_last_event_count = 0

                old_new_events = old_events[old_last_event_count:]
                if old_new_events:
                    incremental_old_session = _copy_session_with_events(
                        old_session, old_new_events
                    )
                    await long_term_memory.add_session_to_memory(
                        incremental_old_session,
                        auto_save_memory_policy=auto_save_memory_policy,
                    )

                    _session_save_cache[old_cache_key] = {
                        "last_save_time": current_time,
                        "last_event_count": old_event_count,
                    }
                    logger.info(
                        f"Previous session `{old_session.id}` saved to long term memory due to session switch."
                    )
                else:
                    logger.info(
                        f"Skipping save for previous session `{old_session.id}`: no new events."
                    )

        # Update active session
        _active_sessions[user_key] = session_id

        session = await session_service.get_session(
            app_name=app_name,
            user_id=user_id,
            session_id=session_id,
        )

        if not session:
            logger.error(
                f"Session {session_id} (app_name={app_name}, user_id={user_id}) not found in session service, cannot save to long-term memory."
            )
            return None

        current_events = getattr(session, "events", [])
        current_event_count = len(current_events)
        # logger.debug(f"Current event count: {current_event_count}")

        # Create cache key
        cache_key = (app_name, user_id, session_id)

        cache_info = _session_save_cache.get(cache_key)
        last_event_count = 0
        throttled = False

        if cache_info:
            last_save_time = cache_info.get("last_save_time", 0)
            last_event_count = cache_info.get("last_event_count", 0)

            if last_event_count > current_event_count:
                logger.warning(
                    f"Saved event cursor for session `{session_id}` "
                    f"({last_event_count}) is greater than current event count "
                    f"({current_event_count}); resetting cursor to 0."
                )
                last_event_count = 0

            time_elapsed = current_time - last_save_time
            new_events_count = current_event_count - last_event_count

            throttled = (
                time_elapsed < MIN_TIME_THRESHOLD
                and new_events_count < MIN_MESSAGES_THRESHOLD
            )
        else:
            logger.info(f"First save for session {session_id}.")

        new_events = current_events[last_event_count:]
        if not new_events:
            logger.info(f"Skipping save for session {session_id}: no new events.")
            return None

        # 阈值没挡住时也要过判定；判定没挡住时也可能因阈值而跳过
        if not await _should_persist(events=new_events, throttled=throttled):
            logger.info(
                f"Skipping save for session {session_id}: "
                f"{len(new_events)} new events were not worth remembering."
            )
            return None

        # Save to long-term memory
        incremental_session = _copy_session_with_events(session, new_events)
        await long_term_memory.add_session_to_memory(
            incremental_session,
            auto_save_memory_policy=auto_save_memory_policy,
        )

        # Update cache
        _session_save_cache[cache_key] = {
            "last_save_time": current_time,
            "last_event_count": current_event_count,
        }

        logger.info(f"Add session `{session.id}` to long term memory.")

        return None

    except AttributeError as e:
        logger.error(f"AttributeError while saving session to memory: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error while saving session to memory: {e}")
        return None
