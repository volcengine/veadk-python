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
    name: str = "user_knowledgebase"

    description: str = "This knowledgebase stores some user-related information."

    backend: Union[
        Literal["local", "opensearch", "viking", "redis"], BaseKnowledgebaseBackend
    ] = "local"
    """Knowledgebase backend type. Supported backends are:
    - local: In-memory knowledgebase, data will be lost when the program exits.
    - opensearch: OpenSearch knowledgebase, requires an OpenSearch cluster.
    - viking: Volcengine VikingDB knowledgebase, requires VikingDB service.
    - redis: Redis knowledgebase, requires Redis with vector search capability.
    Default is `local`."""

    backend_config: dict = Field(default_factory=dict)
    """Configuration for the backend"""

    top_k: int = 10
    """Number of top similar documents to retrieve during search"""

    app_name: str = ""

    index: str = ""
    """The name of the knowledgebase index. If not provided, it will be generated based on the `app_name`."""

    def model_post_init(self, __context: Any) -> None:
        if isinstance(self.backend, BaseKnowledgebaseBackend):
            self._backend = self.backend
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
            f"Initialized knowledgebase with backend {self.backend.__class__.__name__}"
        )

    def add_from_directory(self, directory: str, **kwargs) -> bool:
        """Add knowledge from file path to knowledgebase"""
        return self._backend.add_from_directory(directory=directory, **kwargs)

    def add_from_files(self, files: list[str], **kwargs) -> bool:
        """Add knowledge (e.g, documents, strings, ...) to knowledgebase"""
        return self._backend.add_from_files(files=files, **kwargs)

    def add_from_text(self, text: str | list[str], **kwargs) -> bool:
        """Add knowledge from text to knowledgebase"""
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
