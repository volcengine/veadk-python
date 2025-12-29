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
from google.adk.agents.callback_context import CallbackContext
from veadk.config import getenv
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
                old_events = getattr(old_session, "events", [])
                old_event_count = len(old_events)
                await long_term_memory.add_session_to_memory(old_session)
                old_cache_key = (app_name, user_id, previous_session_id)

                _session_save_cache[old_cache_key] = {
                    "last_save_time": current_time,
                    "last_event_count": old_event_count,
                }
                logger.info(
                    f"Previous session `{old_session.id}` saved to long term memory due to session switch."
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

        if cache_info:
            last_save_time = cache_info.get("last_save_time", 0)
            last_event_count = cache_info.get("last_event_count", 0)

            time_elapsed = current_time - last_save_time
            new_events_count = current_event_count - last_event_count

            # Check if we should skip save
            if (
                time_elapsed < MIN_TIME_THRESHOLD
                and new_events_count < MIN_MESSAGES_THRESHOLD
            ):
                logger.info(
                    f"Skipping save for session {session_id}: "
                    f"only {new_events_count} new events (need {MIN_MESSAGES_THRESHOLD}) "
                    f"and {time_elapsed:.1f}s elapsed (need {MIN_TIME_THRESHOLD}s)"
                )
                return None
        else:
            logger.info(f"First save for session {session_id}.")

        # Save to long-term memory
        await long_term_memory.add_session_to_memory(session)

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
