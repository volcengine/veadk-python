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
import os
import re
import time
import uuid
from typing import Any

from pydantic import Field
from typing_extensions import override

import veadk.config  # noqa E401
from veadk.auth.veauth.utils import get_credential_from_vefaas_iam
from veadk.integrations.ve_viking_db_memory.ve_viking_db_memory import (
    VikingDBMemoryClient,
)
from veadk.memory.long_term_memory_backends.base_backend import (
    BaseLongTermMemoryBackend,
)
from veadk.utils.logger import get_logger

logger = get_logger(__name__)


class VikingDBLTMBackend(BaseLongTermMemoryBackend):
    volcengine_access_key: str | None = Field(
        default_factory=lambda: os.getenv("VOLCENGINE_ACCESS_KEY")
    )

    volcengine_secret_key: str | None = Field(
        default_factory=lambda: os.getenv("VOLCENGINE_SECRET_KEY")
    )

    session_token: str = ""

    region: str = "cn-beijing"
    """VikingDB memory region"""

    memory_type: list[str] = Field(default_factory=list)

    def model_post_init(self, __context: Any) -> None:
        # We get memory type from:
        # 1. user input
        # 2. environment variable
        # 3. default value
        if not self.memory_type:
            env_memory_type = os.getenv("DATABASE_VIKING_MEMORY_TYPE")
            if env_memory_type:
                # "event_1, event_2" -> ["event_1", "event_2"]
                self.memory_type = [x.strip() for x in env_memory_type.split(",")]
            else:
                self.memory_type = ["sys_event_v1", "event_v1"]

        logger.info(f"Using memory type: {self.memory_type}")

        # check whether collection exist, if not, create it
        if not self._collection_exist():
            self._create_collection()

    def precheck_index_naming(self):
        if not (
            isinstance(self.index, str)
            and 1 <= len(self.index) <= 128
            and re.fullmatch(r"^[a-zA-Z][a-zA-Z0-9_]*$", self.index)
        ):
            raise ValueError(
                "The index name does not conform to the rules: it must start with an English letter, contain only letters, numbers, and underscores, and have a length of 1-128."
            )

    def _collection_exist(self) -> bool:
        try:
            client = self._get_client()
            client.get_collection(collection_name=self.index)
            return True
        except Exception:
            return False

    def _create_collection(self) -> None:
        client = self._get_client()
        response = client.create_collection(
            collection_name=self.index,
            description="Created by Volcengine Agent Development Kit VeADK",
            builtin_event_types=["sys_event_v1"],
        )
        return response

    def _get_client(self) -> VikingDBMemoryClient:
        if not (self.volcengine_access_key and self.volcengine_secret_key):
            cred = get_credential_from_vefaas_iam()
            self.volcengine_access_key = cred.access_key_id
            self.volcengine_secret_key = cred.secret_access_key
            self.session_token = cred.session_token

        return VikingDBMemoryClient(
            ak=self.volcengine_access_key,
            sk=self.volcengine_secret_key,
            sts_token=self.session_token,
            region=self.region,
        )

    @override
    def save_memory(self, user_id: str, event_strings: list[str], **kwargs) -> bool:
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

        logger.debug(
            f"Request for add {len(messages)} memory to VikingDB: collection_name={self.index}, metadata={metadata}, session_id={session_id}"
        )

        client = self._get_client()
        response = client.add_messages(
            collection_name=self.index,
            messages=messages,
            metadata=metadata,
            session_id=session_id,
        )

        logger.debug(f"Response from add memory to VikingDB: {response}")

        if not response.get("code") == 0:
            raise ValueError(f"Save VikingDB memory error: {response}")

        return True

    @override
    def search_memory(
        self, user_id: str, query: str, top_k: int, **kwargs
    ) -> list[str]:
        filter = {"user_id": user_id, "memory_type": self.memory_type}

        logger.debug(
            f"Request for search memory in VikingDB: filter={filter}, collection_name={self.index}, query={query}, limit={top_k}"
        )

        client = self._get_client()
        response = client.search_memory(
            collection_name=self.index, query=query, filter=filter, limit=top_k
        )

        logger.debug(f"Response from search memory in VikingDB: {response}")

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
