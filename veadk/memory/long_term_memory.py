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

# adapted from Google ADK memory service adk-python/src/google/adk/memory/vertex_ai_memory_bank_service.py at 0a9e67dbca67789247e882d16b139dbdc76a329a · google/adk-python

import json
from typing import Any, Literal

from google.adk.events.event import Event
from google.adk.memory.base_memory_service import (
    BaseMemoryService,
    SearchMemoryResponse,
)
from google.adk.memory.memory_entry import MemoryEntry
from google.adk.sessions import Session
from google.genai import types
from pydantic import BaseModel, Field
from typing_extensions import override

from veadk.memory.long_term_memory_backends.base_backend import (
    BaseLongTermMemoryBackend,
)
from veadk.memory.long_term_memory_backends.in_memory_backend import InMemoryLTMBackend
from veadk.memory.long_term_memory_backends.opensearch_backend import (
    OpensearchLTMBackend,
)
from veadk.memory.long_term_memory_backends.redis_backend import RedisLTMBackend
from veadk.memory.long_term_memory_backends.vikingdb_memory_backend import (
    VikingDBKnowledgeBackend,
)
from veadk.utils.logger import get_logger

logger = get_logger(__name__)


BACKEND_CLS = {
    "local": InMemoryLTMBackend,
    "opensearch": OpensearchLTMBackend,
    "viking": VikingDBKnowledgeBackend,
    "viking_mem": VikingDBKnowledgeBackend,
    "redis": RedisLTMBackend,
}


def build_long_term_memory_index(app_name: str, user_id: str):
    return f"{app_name}_{user_id}"


class LongTermMemory(BaseMemoryService, BaseModel):
    backend: Literal["local", "opensearch", "redis", "viking", "viking_mem"] = (
        "opensearch"
    )
    """Long term memory backend type"""

    backend_config: dict = Field(default_factory=dict)
    """Long term memory backend configuration"""

    backend_instance: BaseLongTermMemoryBackend | None = None
    """An instance of a long term memory backend that implements the `BaseLongTermMemoryBackend` interface."""

    top_k: int = 5
    """Number of top similar documents to retrieve during search."""

    app_name: str = ""

    user_id: str = ""

    def model_post_init(self, __context: Any) -> None:
        self._backend = None

        if self.backend_instance:
            self._backend = self.backend_instance
            logger.info(
                f"Initialized long term memory with provided backend instance {self._backend.__class__.__name__}"
            )
        else:
            if self.backend_config:
                logger.info(
                    f"Initialized long term memory backend {self.backend} with config."
                )
                self._backend = BACKEND_CLS[self.backend](**self.backend_config)
            elif self.app_name and self.user_id:
                self.index = build_long_term_memory_index(
                    app_name=self.app_name, user_id=self.user_id
                )
                logger.info(f"Long term memory index set to {self.index}.")
                self._backend = BACKEND_CLS[self.backend](
                    **self.backend_config, index=self.index
                )
            else:
                logger.warning(
                    "Neither `backend_instance`, `backend_config`, nor `app_name`/`user_id` is provided, the long term memory storage will initialize when adding a session."
                )

    def _filter_and_convert_events(self, events: list[Event]) -> list[str]:
        final_events = []
        for event in events:
            # filter: bad event
            if not event.content or not event.content.parts:
                continue

            # filter: only add user event to memory to enhance retrieve performance
            if not event.author == "user":
                continue

            # filter: discard function call and function response
            if not event.content.parts[0].text:
                continue

            # convert: to string-format for storage
            message = event.content.model_dump(exclude_none=True, mode="json")

            final_events.append(json.dumps(message, ensure_ascii=False))
        return final_events

    @override
    async def add_session_to_memory(
        self,
        session: Session,
    ):
        app_name = session.app_name
        user_id = session.user_id

        if self.index != build_long_term_memory_index(app_name, user_id):
            logger.warning(
                f"The `app_name` or `user_id` is different from the initialized one, skip add session to memory. Initialized index: {self.index}, current built index: {build_long_term_memory_index(app_name, user_id)}"
            )
            return

        if not self._backend:
            self.index = build_long_term_memory_index(app_name, user_id)
            self._backend = BACKEND_CLS[self.backend](index=self.index)
            logger.info(
                f"Initialize long term memory backend now, index is {self.index}"
            )

        event_strings = self._filter_and_convert_events(session.events)

        logger.info(
            f"Adding {len(event_strings)} events to long term memory: index={self.index}"
        )

        self._backend.save_memory(event_strings=event_strings)

        logger.info(
            f"Added {len(event_strings)} events to long term memory: index={self.index}"
        )

    @override
    async def search_memory(self, *, app_name: str, user_id: str, query: str):
        logger.info(
            f"Searching long term memory: query={query} index={self.index} top_k={self.top_k}"
        )

        # prevent model invoke `load_memory` before add session to this memory
        if not self._backend:
            logger.error(
                "Long term memory backend is not initialized, cannot search memory."
            )
            return SearchMemoryResponse(memories=[])

        memory_chunks = self._backend.search_memory(query=query, top_k=self.top_k)

        memory_events = []
        for memory in memory_chunks:
            try:
                memory_dict = json.loads(memory)
                try:
                    text = memory_dict["parts"][0]["text"]
                    role = memory_dict["role"]
                except KeyError as _:
                    # prevent not a standard text-based event
                    logger.warning(
                        f"Memory content: {memory_dict}. Skip return this memory."
                    )
                    continue
            except json.JSONDecodeError:
                # prevent the memory string is not dumped by `Event` class
                text = memory
                role = "user"

            memory_events.append(
                MemoryEntry(
                    author="user",
                    content=types.Content(parts=[types.Part(text=text)], role=role),
                )
            )

        logger.info(
            f"Return {len(memory_events)} memory events for query: {query} index={self.index}"
        )
        return SearchMemoryResponse(memories=memory_events)
