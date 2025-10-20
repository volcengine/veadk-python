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
from typing_extensions import Union, override

from veadk.memory.long_term_memory_backends.base_backend import (
    BaseLongTermMemoryBackend,
)
from veadk.utils.logger import get_logger

logger = get_logger(__name__)


def _get_backend_cls(backend: str) -> type[BaseLongTermMemoryBackend]:
    match backend:
        case "local":
            from veadk.memory.long_term_memory_backends.in_memory_backend import (
                InMemoryLTMBackend,
            )

            return InMemoryLTMBackend
        case "opensearch":
            from veadk.memory.long_term_memory_backends.opensearch_backend import (
                OpensearchLTMBackend,
            )

            return OpensearchLTMBackend
        case "viking":
            from veadk.memory.long_term_memory_backends.vikingdb_memory_backend import (
                VikingDBLTMBackend,
            )

            return VikingDBLTMBackend
        case "redis":
            from veadk.memory.long_term_memory_backends.redis_backend import (
                RedisLTMBackend,
            )

            return RedisLTMBackend
        case "mem0":
            from veadk.memory.long_term_memory_backends.mem0_backend import (
                Mem0LTMBackend,
            )

            return Mem0LTMBackend

    raise ValueError(f"Unsupported long term memory backend: {backend}")


class LongTermMemory(BaseMemoryService, BaseModel):
    backend: Union[
        Literal["local", "opensearch", "redis", "viking", "viking_mem", "mem0"],
        BaseLongTermMemoryBackend,
    ] = "opensearch"
    """Long term memory backend type"""

    backend_config: dict = Field(default_factory=dict)
    """Long term memory backend configuration"""

    top_k: int = 5
    """Number of top similar documents to retrieve during search."""

    index: str = ""

    app_name: str = ""

    user_id: str = ""
    """Deprecated attribute"""

    def model_post_init(self, __context: Any) -> None:
        # Once user define a backend instance, use it directly
        if isinstance(self.backend, BaseLongTermMemoryBackend):
            self._backend = self.backend
            self.index = self._backend.index
            logger.info(
                f"Initialized long term memory with provided backend instance {self._backend.__class__.__name__}, index={self.index}"
            )
            return

        # Once user define backend config, use it directly
        if self.backend_config:
            self._backend = _get_backend_cls(self.backend)(**self.backend_config)
            return

        # Check index
        self.index = self.index or self.app_name
        if not self.index:
            logger.warning(
                "Attribute `index` or `app_name` not provided, use `default_app` instead."
            )
            self.index = "default_app"

        # Forward compliance
        if self.backend == "viking_mem":
            logger.warning(
                "The `viking_mem` backend is deprecated, change to `viking` instead."
            )
            self.backend = "viking"

        self._backend = _get_backend_cls(self.backend)(index=self.index)

        logger.info(
            f"Initialized long term memory with provided backend instance {self._backend.__class__.__name__}, index={self.index}"
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
        user_id = session.user_id
        event_strings = self._filter_and_convert_events(session.events)

        logger.info(
            f"Adding {len(event_strings)} events to long term memory: index={self.index}"
        )
        self._backend.save_memory(user_id=user_id, event_strings=event_strings)
        logger.info(
            f"Added {len(event_strings)} events to long term memory: index={self.index}, user_id={user_id}"
        )

    @override
    async def search_memory(
        self, *, app_name: str, user_id: str, query: str
    ) -> SearchMemoryResponse:
        logger.info(f"Search memory with query={query}")

        memory_chunks = []
        try:
            memory_chunks = self._backend.search_memory(
                query=query, top_k=self.top_k, user_id=user_id
            )
        except Exception as e:
            logger.error(
                f"Exception orrcus during memory search: {e}. Return empty memory chunks"
            )

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
            f"Return {len(memory_events)} memory events for query: {query} index={self.index} user_id={user_id}"
        )
        return SearchMemoryResponse(memories=memory_events)
