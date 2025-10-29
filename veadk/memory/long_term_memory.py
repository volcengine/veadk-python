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
    """Manages long-term memory storage and retrieval for applications.

    This class provides an interface to store, retrieve, and manage long-term
    contextual information using different backend types (e.g., OpenSearch, Redis).
    It supports configuration of the backend service and retrieval behavior.

    Attributes:
        backend (Union[Literal["local", "opensearch", "redis", "viking", "viking_mem", "mem0"], BaseLongTermMemoryBackend]):
            The type or instance of the long-term memory backend. Defaults to "opensearch".

        backend_config (dict):
            Configuration parameters for the selected backend. Defaults to an empty dictionary.

        top_k (int):
            The number of top similar documents to retrieve during search. Defaults to 5.

        index (str):
            The name of the index or collection used for storing memory items. Defaults to an empty string.

        app_name (str):
            The name of the application that owns this memory instance. Defaults to an empty string.

        user_id (str):
            Deprecated attribute. Retained for backward compatibility. Defaults to an empty string.

    Notes:
        Please ensure that you have set the embedding-related configurations in environment variables.

    Examples:
        ### Simple long-term memory

        Once create a long-term memory withou any arguments, all configurations are come from **environment variables**.

        ```python
        import asyncio

        from veadk import Agent, Runner
        from veadk.memory.long_term_memory import LongTermMemory
        from veadk.memory.short_term_memory import ShortTermMemory

        app_name = "veadk_playground_app"
        user_id = "veadk_playground_user"

        long_term_memory = LongTermMemory(backend="local", app_name=app_name)

        agent = Agent(long_term_memory=long_term_memory)

        runner = Runner(
            agent=agent,
            app_name=app_name,
            user_id=user_id,
            short_term_memory=ShortTermMemory(),
        )

        # ===== add memory =====
        session_id = "veadk_playground_session"
        teaching_prompt = "I brought an ice-cream last week."

        asyncio.run(runner.run(messages=teaching_prompt, session_id=session_id))
        asyncio.run(
            runner.save_session_to_long_term_memory(session_id=session_id)
        )  # save session to long-term memory


        # ===== check memory =====
        session_id = "veadk_playground_session_2"  # use a new session
        student_prompt = "What I brought last week?"

        response = asyncio.run(runner.run(messages=student_prompt, session_id=session_id))

        print(response)
        ```

        ### Create with a backend instance

        ```python
        from veadk.memory.long_term_memory import LongTermMemory
        from veadk.memory.long_term_memory.backends import LongTermMemory

        long_term_memory = LongTermMemory(backend=...)
        ```

        ### Create with backend configurations

        ```python
        from veadk.memory.long_term_memory import LongTermMemory

        long_term_memory = LongTermMemory(backend="", backend_config={})
        ```
    """

    backend: Union[
        Literal["local", "opensearch", "redis", "viking", "viking_mem", "mem0"],
        BaseLongTermMemoryBackend,
    ] = "opensearch"

    backend_config: dict = Field(default_factory=dict)

    top_k: int = 5

    index: str = ""

    app_name: str = ""

    user_id: str = ""

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
            if "index" not in self.backend_config:
                logger.warning(
                    "Attribute `index` not provided in backend_config, use `index` or `app_name` instead."
                )
                self.backend_config["index"] = self.index or self.app_name

            logger.debug(
                f"Init {self.backend}, Use provided backend config: {self.backend_config}"
            )
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
        """Add a chat session's events to the long-term memory backend.

        This method extracts and filters the events from a given `Session` object,
        converts them into serialized strings, and stores them into the long-term
        memory system. It is typically called after a chat session ends or when
        important contextual data needs to be persisted for future retrieval.

        Args:
            session (Session):
                The session object containing user ID and a list of events to persist.

        Examples:
            ```python
            session = Session(
                user_id="user_123",
                events=[
                    Event(role="user", content="I like Go and Rust."),
                    Event(role="assistant", content="Got it! I'll remember that."),
                ]
            )

            await memory_service.add_session_to_memory(session)
            # Logs:
            # Adding 2 events to long term memory: index=main
            # Added 2 events to long term memory: index=main, user_id=user_123
            ```
        """
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
        """Search memory entries for a given user and query.

        This method queries the memory backend to retrieve the most relevant stored
        memory chunks for a given user and text query. It then converts those raw
        memory chunks into structured `MemoryEntry` objects to be returned to the caller.

        Args:
            app_name (str): Name of the application requesting the memory search.
            user_id (str): Unique identifier for the user whose memory is being queried.
            query (str): The text query to match against stored memory content.

        Returns:
            SearchMemoryResponse:
                An object containing a list of `MemoryEntry` items representing
                the retrieved memory snippets relevant to the query.

        Examples:
            ```python
            response = await memory_service.search_memory(
                app_name="chat_app",
                user_id="user_123",
                query="favorite programming language"
            )

            for memory in response.memories:
                print(memory.content.parts[0].text)
            # Output:
            # User likes Python and TypeScript for backend development.
            ```
        """
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
