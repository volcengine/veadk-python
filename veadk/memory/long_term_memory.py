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

from google.adk.memory.base_memory_service import (
    BaseMemoryService,
    SearchMemoryResponse,
)
from google.adk.memory.memory_entry import MemoryEntry
from google.adk.sessions import Session
from google.genai import types
from typing_extensions import override

from veadk.database import DatabaseFactory
from veadk.utils.logger import get_logger

from .memory_database_adapter import get_memory_adapter

logger = get_logger(__name__)


class LongTermMemory(BaseMemoryService):
    def __init__(
        self,
        backend: Literal[
            "local", "opensearch", "redis", "mysql", "viking"
        ] = "opensearch",
        top_k: int = 5,
    ):
        if backend == "viking":
            backend = "viking_mem"
        self.top_k = top_k
        self.backend = backend

        logger.info(
            f"Initializing long term memory: backend={self.backend} top_k={self.top_k}"
        )

        self.db_client = DatabaseFactory.create(
            backend=backend,
        )

        self.adapter = get_memory_adapter(backend)(database_client=self.db_client)

        logger.info(
            f"Initialized long term memory: db_client={self.db_client} adapter={self.adapter}"
        )

    @override
    async def add_session_to_memory(
        self,
        session: Session,
    ):
        event_list = []
        for event in session.events:
            if not event.content or not event.content.parts:
                continue
            if not event.author == "user":  # we only add user event to memory
                continue

            message = event.content.model_dump(exclude_none=True, mode="json")
            if (
                "text" not in message["parts"][0]
            ):  # remove function_call & function_resp
                continue
            event_list.append(json.dumps(message))
        self.adapter.add(
            event_list,
            app_name=session.app_name,
            user_id=session.user_id,
            session_id=session.id,
        )

        logger.info(
            f"Added {len(event_list)} events to long term memory: app_name={session.app_name} user_id={session.user_id} session_id={session.id}"
        )

    @override
    async def search_memory(self, *, app_name: str, user_id: str, query: str):
        logger.info(
            f"Searching long term memory: query={query} app_name={app_name} user_id={user_id}"
        )
        memory_chunks = self.adapter.query(
            query=query,
            app_name=app_name,
            user_id=user_id,
        )
        if len(memory_chunks) == 0:
            logger.info(
                f"Found no memory chunks for query: {query} app_name={app_name} user_id={user_id}"
            )
            return SearchMemoryResponse()

        logger.info(
            f"Found {len(memory_chunks)} memory chunks for query: {query} app_name={app_name} user_id={user_id}"
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
                # prevent the memory string is not dumped by `event`
                text = memory
                role = "user"

            memory_events.append(
                MemoryEntry(
                    author="user",
                    content=types.Content(parts=[types.Part(text=text)], role=role),
                )
            )

        logger.info(
            f"Return {len(memory_events)} memory events for query: {query} app_name={app_name} user_id={user_id}"
        )
        return SearchMemoryResponse(memories=memory_events)

    @override
    async def delete_memory(self, *, app_name: str, user_id: str):
        self.adapter.delete(
            app_name=app_name,
            user_id=user_id,
            session_id="",  # session_id is not used in the adapter delete method
        )
