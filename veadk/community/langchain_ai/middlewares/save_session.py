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

from __future__ import annotations

from langchain.agents import AgentState
from langchain.agents.middleware import after_agent
from langchain_core.messages.ai import AIMessage
from langchain_core.messages.human import HumanMessage
from langgraph.runtime import Runtime

from veadk.community.langchain_ai.store.memory.viking_memory import (
    VikingMemoryStore,
)
from veadk.utils.logger import get_logger

logger = get_logger(__name__)


@after_agent
def save_session(state: AgentState, runtime: Runtime) -> None:
    """Save the session to the memory store."""
    store: VikingMemoryStore | None = runtime.store
    if not store:
        return

    app_name = store.index
    user_id = runtime.context.user_id
    session_id = runtime.context.session_id

    messages = state.get("messages", [])
    logger.debug(
        f"Save session {session_id} for user {user_id} with {len(messages)} messages. messages={messages}"
    )

    events = {}
    for message in messages:
        print(type(message))
        if isinstance(message, HumanMessage):
            event = {"role": "user", "parts": [{"text": message.content}]}

        elif isinstance(message, AIMessage):
            event = {"role": "assistant", "parts": [{"text": message.content}]}
        else:
            ...

        events[message.id] = event

    store.put(namespace=(app_name, user_id), key=session_id, value=events)
