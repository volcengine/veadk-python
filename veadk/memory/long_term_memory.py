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
from typing import Literal

from google.adk.events.event import Event
from google.adk.memory.base_memory_service import (
    BaseMemoryService,
    SearchMemoryResponse,
)
from google.adk.memory.memory_entry import MemoryEntry
from google.adk.sessions import Session
from google.genai import types
from typing_extensions import override

from veadk.database import DatabaseFactory
from veadk.database.database_adapter import get_long_term_memory_database_adapter
from veadk.utils.logger import get_logger

logger = get_logger(__name__)


def build_long_term_memory_index(app_name: str, user_id: str):
    return f"{app_name}_{user_id}"


class LongTermMemory(BaseMemoryService):
    def __init__(
        self,
        backend: Literal[
            "local", "opensearch", "redis", "mysql", "viking", "viking_mem"
        ] = "opensearch",
        top_k: int = 5,
    ):
        if backend == "viking":
            logger.warning(
                "`viking` backend is deprecated, switching to `viking_mem` backend."
            )
            backend = "viking_mem"
        self.top_k = top_k
        self.backend = backend

        logger.info(
            f"Initializing long term memory: backend={self.backend} top_k={self.top_k}"
        )

        self.db_client = DatabaseFactory.create(
            backend=backend,
        )
        self.adapter = get_long_term_memory_database_adapter(self.db_client)

        logger.info(
            f"Initialized long term memory: db_client={self.db_client} adapter={self.adapter}"
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
        event_strings = self._filter_and_convert_events(session.events)
        index = build_long_term_memory_index(session.app_name, session.user_id)

        logger.info(
            f"Adding {len(event_strings)} events to long term memory: index={index}"
        )

        # check if viking memory database, should give a user id： if/else
        if self.backend == "viking_mem":
            self.adapter.add(data=event_strings, index=index, user_id=session.user_id)
        else:
            self.adapter.add(data=event_strings, index=index)

        logger.info(
            f"Added {len(event_strings)} events to long term memory: index={index}"
        )

    @override
    async def search_memory(self, *, app_name: str, user_id: str, query: str):
        index = build_long_term_memory_index(app_name, user_id)

        logger.info(
            f"Searching long term memory: query={query} index={index} top_k={self.top_k}"
        )

        # user id if viking memory db
        if self.backend == "viking_mem":
            memory_chunks = self.adapter.query(
                query=query, index=index, top_k=self.top_k, user_id=user_id
            )
        else:
            memory_chunks = self.adapter.query(
                query=query, index=index, top_k=self.top_k
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
            f"Return {len(memory_events)} memory events for query: {query} index={index}"
        )
        return SearchMemoryResponse(memories=memory_events)
