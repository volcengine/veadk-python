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

import json
import re
import time
import uuid
from typing import Any

from pydantic import Field
from typing_extensions import override

import veadk.config  # noqa E401
from veadk.config import getenv
from veadk.memory.long_term_memory_backends.base_backend import (
    BaseLongTermMemoryBackend,
)
from veadk.utils.logger import get_logger

try:
    from mcp_server_vikingdb_memory.common.memory_client import VikingDBMemoryService
except ImportError:
    raise ImportError(
        "Please install VeADK extensions\npip install veadk-python[extensions]"
    )

logger = get_logger(__name__)


class VikingDBLTMBackend(BaseLongTermMemoryBackend):
    volcengine_access_key: str = Field(
        default_factory=lambda: getenv("VOLCENGINE_ACCESS_KEY")
    )

    volcengine_secret_key: str = Field(
        default_factory=lambda: getenv("VOLCENGINE_SECRET_KEY")
    )

    region: str = "cn-beijing"
    """VikingDB memory region"""

    def precheck_index_naming(self):
        if not (
            isinstance(self.index, str)
            and 1 <= len(self.index) <= 128
            and re.fullmatch(r"^[a-zA-Z][a-zA-Z0-9_]*$", self.index)
        ):
            raise ValueError(
                "The index name does not conform to the rules: it must start with an English letter, contain only letters, numbers, and underscores, and have a length of 1-128."
            )

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
        try:
            self._client.get_collection(collection_name=self.index)
            return True
        except Exception:
            return False

    def _create_collection(self) -> None:
        response = self._client.create_collection(
            collection_name=self.index,
            description="Created by Volcengine Agent Development Kit VeADK",
            builtin_event_types=["sys_event_v1"],
        )
        return response

    @override
    def save_memory(self, event_strings: list[str], **kwargs) -> bool:
        user_id = kwargs.get("user_id")
        if user_id is None:
            raise ValueError("user_id is required")
        session_id = str(uuid.uuid1())
        messages = []
        for raw_events in event_strings:
            event = json.loads(raw_events)
            content = event["parts"][0]["text"]
            role = (
                "user" if event["role"] == "user" else "assistant"
            )  # field 'role': viking memory only allow 'assistant','system','user',
            messages.append({"role": role, "content": content})
        metadata = {
            "default_user_id": user_id,
            "default_assistant_id": "assistant",
            "time": int(time.time() * 1000),
        }
        response = self._client.add_messages(
            collection_name=self.index,
            messages=messages,
            metadata=metadata,
            session_id=session_id,
        )

        if not response.get("code") == 0:
            raise ValueError(f"Save VikingDB memory error: {response}")

        return True

    @override
    def search_memory(self, query: str, top_k: int, **kwargs) -> list[str]:
        user_id = kwargs.get("user_id")
        if user_id is None:
            raise ValueError("user_id is required")
        filter = {
            "user_id": user_id,
            "memory_type": ["sys_event_v1"],
        }
        response = self._client.search_memory(
            collection_name=self.index, query=query, filter=filter, limit=top_k
        )

        if not response.get("code") == 0:
            raise ValueError(f"Search VikingDB memory error: {response}")

        result = response.get("data", {}).get("result_list", [])
        if result:
            return [
                json.dumps(
                    {
                        "role": "user",
                        "parts": [{"text": r.get("memory_info").get("summary")}],
                    },
                    ensure_ascii=False,
                )
                for r in result
            ]
        return []
