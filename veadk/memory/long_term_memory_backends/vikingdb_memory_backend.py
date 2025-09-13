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

import uuid
from typing import Any

from mcp_server_vikingdb_memory.common.memory_client import VikingDBMemoryService
from pydantic import Field
from typing_extensions import override

from veadk.config import getenv
from veadk.memory.long_term_memory_backends.base_backend import (
    BaseLongTermMemoryBackend,
)
from veadk.utils.logger import get_logger

logger = get_logger(__name__)


class VikingDBKnowledgeBackend(BaseLongTermMemoryBackend):
    volcengine_access_key: str = Field(
        default_factory=lambda: getenv("VOLCENGINE_ACCESS_KEY")
    )

    volcengine_secret_key: str = Field(
        default_factory=lambda: getenv("VOLCENGINE_SECRET_KEY")
    )

    region: str = "cn-beijing"
    """VikingDB memory region"""

    def model_post_init(self, __context: Any) -> None:
        self._client = VikingDBMemoryService(
            ak=self.volcengine_access_key,
            sk=self.volcengine_secret_key,
            region=self.region,
        )

        # check whether collection exist, if not, create it
        if not self._collection_exist():
            self._create_collection()

    def _collection_exist(self) -> bool:
        response = self._client.get_collection(collection_name=self.index)
        return response is not None

    def _create_collection(self) -> None:
        response = self._client.create_collection(
            collection_name=self.index,
            description="Created by Volcengine Agent Development Kit VeADK",
        )
        return response

    @override
    def save_memory(self, event_strings: list[str], **kwargs) -> bool:
        session_id = uuid.uuid1()
        response = self._client.add_messages(
            collection_name=self.index,
            messages=event_strings,
            metadata={},
            session_id=session_id,
        )

        if not response.get("code") == 0:
            raise ValueError(f"Save VikingDB memory error: {response}")

        return True

    @override
    def search_memory(self, query: str, top_k: int, **kwargs) -> list[str]:
        response = self._client.search_memory(
            collection_name=self.index, query=query, filter={}
        )

        if not response.get("code") == 0:
            raise ValueError(f"Search VikingDB memory error: {response}")

        response = response.get("data", {}).get("results", [])
        return []
