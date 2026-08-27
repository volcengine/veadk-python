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

"""Preview how auto_save_memory_policy filters long-term-memory events.

The real auto-save path reads `Agent.auto_save_memory_policy` and passes it to
`LongTermMemory.add_session_to_memory` after an agent turn. This example avoids
calling an LLM and uses a recording backend so you can see exactly which events
each policy would persist.
"""

import asyncio
import json

from google.adk.events import Event
from google.adk.sessions import Session
from google.genai import types
from pydantic import Field

from veadk import Agent
from veadk.memory import MemoryAutoSavePolicy
from veadk.memory.long_term_memory import LongTermMemory
from veadk.memory.long_term_memory_backends.base_backend import (
    BaseLongTermMemoryBackend,
)

APP_NAME = "ltm_policy_demo"
USER_ID = "user-42"


class RecordingLongTermMemoryBackend(BaseLongTermMemoryBackend):
    saved_events: list[str] = Field(default_factory=list)

    def precheck_index_naming(self):
        pass

    def save_memory(self, user_id: str, event_strings: list[str], **kwargs) -> bool:
        del user_id, kwargs
        self.saved_events.extend(event_strings)
        return True

    def search_memory(
        self, user_id: str, query: str, top_k: int, **kwargs
    ) -> list[str]:
        del user_id, query, top_k, kwargs
        return []


def build_agent(
    policy: str | MemoryAutoSavePolicy,
) -> tuple[Agent, RecordingLongTermMemoryBackend]:
    backend = RecordingLongTermMemoryBackend(index=APP_NAME)
    agent = Agent(
        name="ltm_policy_agent",
        model_name="not-used",
        model_provider="test",
        model_api_key="not-used",
        model_api_base="http://localhost",
        instruction="Preview long-term-memory auto-save policy behavior.",
        long_term_memory=LongTermMemory(backend=backend, app_name=APP_NAME),
        auto_save_session=True,
        auto_save_memory_policy=policy,
    )
    return agent, backend


def build_session() -> Session:
    return Session(
        id="session-1",
        app_name=APP_NAME,
        user_id=USER_ID,
        state={},
        events=[
            Event(
                author="user",
                content=types.Content(
                    role="user",
                    parts=[types.Part(text="Remember that I prefer short answers.")],
                ),
            ),
            Event(
                author="assistant",
                content=types.Content(
                    role="model",
                    parts=[types.Part(text="Got it. I will keep answers concise.")],
                ),
            ),
            Event(
                author="assistant",
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part(
                            function_call=types.FunctionCall(
                                id="call-1",
                                name="load_memory",
                                args={"query": "answer style"},
                            )
                        )
                    ],
                ),
            ),
            Event(
                author="user",
                content=types.Content(
                    role="user",
                    parts=[
                        types.Part(
                            function_response=types.FunctionResponse(
                                id="call-1",
                                name="load_memory",
                                response={"result": "short answers"},
                            )
                        )
                    ],
                ),
            ),
            Event(
                author="assistant",
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part(text="internal reasoning", thought=True),
                        types.Part(text="Final answer text."),
                    ],
                ),
            ),
            Event(
                author="user",
                content=types.Content(
                    role="user",
                    parts=[
                        types.Part(
                            inline_data=types.Blob(
                                mime_type="text/plain",
                                data=b"raw payload",
                            )
                        )
                    ],
                ),
            ),
        ],
    )


def compact_policy(policy: str | MemoryAutoSavePolicy) -> str:
    if isinstance(policy, str):
        return policy
    return json.dumps(policy.model_dump(exclude_none=True), ensure_ascii=False)


async def preview_policy(policy: str | MemoryAutoSavePolicy) -> None:
    agent, backend = build_agent(policy)
    assert agent.long_term_memory is not None
    await agent.long_term_memory.add_session_to_memory(
        build_session(),
        auto_save_memory_policy=agent.auto_save_memory_policy,
    )
    print(f"\nPolicy: {compact_policy(policy)}")
    for index, event_string in enumerate(backend.saved_events, start=1):
        event = json.loads(event_string)
        print(f"{index}. role={event.get('role')} author={event.get('author')}")
        print(json.dumps(event.get("parts", []), ensure_ascii=False, indent=2))


async def main() -> None:
    await preview_policy("default")
    await preview_policy("all")
    await preview_policy(
        MemoryAutoSavePolicy(
            preset="custom",
            include_roles=["user", "assistant"],
            include_event_types=["text", "function_call", "function_response"],
            include_thought=False,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
