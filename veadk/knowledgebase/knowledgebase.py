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

from typing import Any, Callable, Literal, Union

from pydantic import BaseModel, Field

from veadk.knowledgebase.backends.base_backend import BaseKnowledgebaseBackend
from veadk.knowledgebase.entry import KnowledgebaseEntry
from veadk.utils.logger import get_logger

logger = get_logger(__name__)


def _get_backend_cls(backend: str) -> type[BaseKnowledgebaseBackend]:
    match backend:
        case "local":
            from veadk.knowledgebase.backends.in_memory_backend import (
                InMemoryKnowledgeBackend,
            )

            return InMemoryKnowledgeBackend
        case "opensearch":
            from veadk.knowledgebase.backends.opensearch_backend import (
                OpensearchKnowledgeBackend,
            )

            return OpensearchKnowledgeBackend
        case "viking":
            from veadk.knowledgebase.backends.vikingdb_knowledge_backend import (
                VikingDBKnowledgeBackend,
            )

            return VikingDBKnowledgeBackend
        case "redis":
            from veadk.knowledgebase.backends.redis_backend import (
                RedisKnowledgeBackend,
            )

            return RedisKnowledgeBackend

    raise ValueError(f"Unsupported knowledgebase backend: {backend}")


class KnowledgeBase(BaseModel):
    """A knowledge base for storing user-related information.

    This class represents a knowledge base used to store and retrieve user-specific data.
    It supports multiple backend options, including in-memory, OpenSearch, Redis, and Volcengine's
    VikingDB. The knowledge base allows for efficient document retrieval based on similarity,
    with the ability to configure backend-specific settings.

    Attributes:
        name (str): The name of the knowledge base. Default is "user_knowledgebase".
        description (str): A description of the knowledge base. Default is "This knowledgebase stores some user-related information."
        backend (Union[Literal["local", "opensearch", "viking", "redis"], BaseKnowledgebaseBackend]):
            The type of backend to use for storing and querying the knowledge base. Supported options include:
            - 'local' for in-memory storage (data is lost when the program exits).
            - 'opensearch' for OpenSearch (requires OpenSearch cluster).
            - 'viking' for Volcengine VikingDB (requires VikingDB service).
            - 'redis' for Redis with vector search capability (requires Redis).
            Default is 'local'.
        backend_config (dict): Configuration dictionary for the selected backend.
        top_k (int): The number of top similar documents to retrieve during a search. Default is 10.
        app_name (str): The name of the application associated with the knowledge base. If index is not provided, this value will be set to `index`.
        index (str): The name of the knowledge base index.

    Notes:
        Please ensure that you have set the embedding-related configurations in environment variables.

    Examples:
        ### Simple backend

        Create a local knowledgebase:

        ```python
        from veadk import Agent, Runner
        from veadk.knowledgebase.knowledgebase import KnowledgeBase
        from veadk.memory.short_term_memory import ShortTermMemory

        app_name = "veadk_playground_app"
        user_id = "veadk_playground_user"
        session_id = "veadk_playground_session"


        knowledgebase = KnowledgeBase(backend="opensearch", app_name=app_name)
        knowledgebase.add_from_files(files=[knowledgebase_file])

        agent = Agent(knowledgebase=knowledgebase)

        runner = Runner(
            agent=agent,
            short_term_memory=ShortTermMemory(),
            app_name=app_name,
            user_id=user_id,
        )

        response = await runner.run(
            messages="Tell me the secret of green.", session_id=session_id
        )
        print(response)
        ```

        ### Initialize knowledgebase with metadata

        ```python
        from veadk.knowledgebase import KnowledgeBase

        knowledgebase = KnowledgeBase(
            name="user_data",
            description="A knowledgebase contains user hobbies.",
            index="my_app",
        )
        ```

        ### Initialize knowledgebase with backend instance

        ```python
        import veadk.config  # noqa

        from veadk.knowledgebase import KnowledgeBase
        from veadk.knowledgebase.backends.in_memory_backend import InMemoryKnowledgeBackend

        backend = InMemoryKnowledgeBackend(
            index="my_app",
            embedding_config=...,
        )

        knowledgebase = KnowledgeBase(
            name="user_data",
            description="A knowledgebase contains user hobbies.",
            backend=backend,
        )
        ```

        ### Initialize knowledgebase with backend config

        ```python
        from veadk.knowledgebase import KnowledgeBase

        knowledgebase = KnowledgeBase(
            name="user_data",
            description="A knowledgebase contains user hobbies.",
            backend="local",
            backend_config={"index": "user_app"},
        )
        ```
    """

    name: str = "user_knowledgebase"

    description: str = "This knowledgebase stores some user-related information."

    backend: Union[
        Literal["local", "opensearch", "viking", "redis"], BaseKnowledgebaseBackend
    ] = "local"

    backend_config: dict = Field(default_factory=dict)

    top_k: int = 10

    app_name: str = ""

    index: str = ""

    def model_post_init(self, __context: Any) -> None:
        if isinstance(self.backend, BaseKnowledgebaseBackend):
            self._backend = self.backend
            self.index = self._backend.index
            logger.info(
                f"Initialized knowledgebase with provided backend instance {self._backend.__class__.__name__}"
            )
            return

        # Once user define backend config, use it directly
        if self.backend_config:
            self._backend = _get_backend_cls(self.backend)(**self.backend_config)
            return

        self.index = self.index or self.app_name
        if not self.index:
            raise ValueError("Either `index` or `app_name` must be provided.")

        logger.info(
            f"Initializing knowledgebase: backend={self.backend} index={self.index} top_k={self.top_k}"
        )
        self._backend = _get_backend_cls(self.backend)(index=self.index)
        logger.info(
            f"Initialized knowledgebase with backend {self._backend.__class__.__name__}"
        )

    def add_from_directory(self, directory: str, **kwargs) -> bool:
        """Add knowledge from file path to knowledgebase.

        Add the files in the directory to knowledgebase backend.

        Args:
            directory (str): The directory path that needs to store.

        Returns:
            bool: True if successfully store the knowledgebase, False otherwise.

        Examples:
            Store a directory to knowledgebase:

            ```python
            knowledgebase = Knowledgebase(backend="local")

            if knowledgebase.add_from_directory("./knowledgebase"):
                # add successfully
                ...
            else:
                raise RuntimeError("Uploaded directory failed.")
            ```
        """
        return self._backend.add_from_directory(directory=directory, **kwargs)

    def add_from_files(self, files: list[str], **kwargs) -> bool:
        """Add knowledge files to knowledgebase.

        Add a list of files to knowledgebase backend.

        Args:
            files (str): The list of files.

        Returns:
            bool: True if successfully store the knowledgebase, False otherwise.

        Examples:
            Store files to knowledgebase:

            ```python
            knowledgebase = Knowledgebase(backend="local")

            if knowledgebase.add_from_files("./knowledgebase"):
                # add successfully
                ...
            else:
                raise RuntimeError("Uploaded files failed.")
            ```
        """
        return self._backend.add_from_files(files=files, **kwargs)

    def add_from_text(self, text: str | list[str], **kwargs) -> bool:
        """Add a piece of text or a list of text to knowledgebase.

        The `text` can be a string or a list of string. The text will be embedded and stored by the corresponding backend.

        Args:
            text (str | list[str]): The text string or a list of text strings.

        Returns:
            bool: True if successfully store the knowledgebase, False otherwise.

        Examples:
            Store a string or a list of string to knowledgebase:

            ```python
            knowledgebase = Knowledgebase(backend="local")

            if knowledgebase.add_from_text("./knowledgebase"):
                # add successfully
                ...
            else:
                raise RuntimeError("Uploaded text failed.")
            ```
        """
        return self._backend.add_from_text(text=text, **kwargs)

    def search(self, query: str, top_k: int = 0, **kwargs) -> list[KnowledgebaseEntry]:
        """Search knowledge from knowledgebase"""
        top_k = top_k if top_k != 0 else self.top_k

        _entries = self._backend.search(query=query, top_k=top_k, **kwargs)

        entries = []
        for entry in _entries:
            if isinstance(entry, KnowledgebaseEntry):
                entries.append(entry)
            elif isinstance(entry, str):
                entries.append(KnowledgebaseEntry(content=entry))
            else:
                logger.error(
                    f"Unsupported entry type from backend search method: {type(entry)} with {entry}. Expected `KnowledgebaseEntry` or `str`. Skip for this entry."
                )

        return entries

    def __getattr__(self, name) -> Callable:
        """In case of knowledgebase have no backends' methods (`delete`, `list_chunks`, etc)

        For example, knowledgebase.delete(...) -> self._backend.delete(...)
        """
        return getattr(self._backend, name)
