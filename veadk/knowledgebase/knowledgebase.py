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

from typing import Any, Callable, Literal

from pydantic import BaseModel, Field

from veadk.knowledgebase.backends.base_backend import BaseKnowledgebaseBackend
from veadk.knowledgebase.backends.in_memory_backend import InMemoryKnowledgeBackend
from veadk.knowledgebase.backends.opensearch_backend import OpensearchKnowledgeBackend
from veadk.knowledgebase.backends.redis_backend import RedisKnowledgeBackend
from veadk.knowledgebase.backends.vikingdb_knowledge_backend import (
    VikingDBKnowledgeBackend,
)
from veadk.utils.logger import get_logger

logger = get_logger(__name__)


BACKEND_CLS = {
    "local": InMemoryKnowledgeBackend,
    "opensearch": OpensearchKnowledgeBackend,
    "viking": VikingDBKnowledgeBackend,
    "redis": RedisKnowledgeBackend,
}


def build_knowledgebase_index(app_name: str):
    return f"veadk_kb_{app_name}"


class KnowledgeBase(BaseModel):
    backend: Literal["local", "opensearch", "viking", "redis"] = "local"
    """Knowledgebase backend type. Supported backends are:
    - local: In-memory knowledgebase, data will be lost when the program exits.
    - opensearch: OpenSearch knowledgebase, requires an OpenSearch cluster.
    - viking: Volcengine VikingDB knowledgebase, requires VikingDB service.
    - redis: Redis knowledgebase, requires Redis with vector search capability.
    Default is `local`."""

    backend_config: dict = Field(default_factory=dict)
    """Configuration for the backend"""

    backend_instance: BaseKnowledgebaseBackend | None = None
    """An instance of a knowledgebase backend that implements the `BaseKnowledgebaseBackend` interface."""

    top_k: int = 10
    """Number of top similar documents to retrieve during search. 
    
    Default is 10."""

    app_name: str = ""

    index: str = ""
    """The name of the knowledgebase index. If not provided, it will be generated based on the `app_name`."""

    def model_post_init(self, __context: Any) -> None:
        if not self.app_name and not self.index:
            raise ValueError(
                "Either `app_name` or `index` must be provided one of them."
            )

        if self.app_name and self.index:
            logger.warning(
                "`app_name` and `index` are both provided, using `index` as the knowledgebase index name."
            )

        if self.app_name and not self.index:
            self.index = build_knowledgebase_index(self.app_name)

        if self.backend_instance:
            self._backend = self.backend_instance
            logger.info(
                f"Initialized knowledgebase with provided backend instance {self._backend.__class__.__name__}"
            )
        else:
            logger.info(
                f"Initializing knowledgebase: backend={self.backend} top_k={self.top_k}"
            )
            self._backend = BACKEND_CLS[self.backend](
                index=self.index, **self.backend_config
            )
            logger.info(
                f"Initialized knowledgebase with backend {self._backend.__class__.__name__}"
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

    def search(self, query: str, top_k: int = 0, **kwargs) -> list[str]:
        """Search knowledge from knowledgebase"""
        if top_k == 0:
            top_k = self.top_k
        return self._backend.search(query=query, top_k=top_k, **kwargs)

    def __getattr__(self, name) -> Callable:
        """In case of knowledgebase have no backends' methods (`delete`, `list_chunks`, etc)

        For example, knowledgebase.delete(...) -> self._backend.delete(...)
        """
        return getattr(self._backend, name)
