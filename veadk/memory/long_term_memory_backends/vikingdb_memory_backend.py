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
from vikingdb import IAM
from vikingdb.memory import VikingMem

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

    cloud_provider: str = Field(
        default_factory=lambda: os.getenv("CLOUD_PROVIDER", "volces")
    )

    region: str = Field(default="")
    """VikingDB memory region"""

    volcengine_project: str = Field(
        default_factory=lambda: os.getenv("DATABASE_VIKINGMEM_PROJECT") or "default"
    )
    """VikingDB memory project"""

    memory_type: list[str] = Field(default_factory=list)

    def model_post_init(self, __context: Any) -> None:
        if not self.region:
            if self.cloud_provider.lower() == "byteplus":
                self.region = os.getenv("DATABASE_VIKING_REGION", "cn-hongkong")
            else:
                self.region = os.getenv("DATABASE_VIKING_REGION", "cn-beijing")

        # We get memory type from:
        # 1. user input
        # 2. environment variable
        # 3. default value
        if not self.memory_type:
            env_memory_type = os.getenv("DATABASE_VIKINGMEM_MEMORY_TYPE")
            if env_memory_type:
                # "event_1, event_2" -> ["event_1", "event_2"]
                self.memory_type = [x.strip() for x in env_memory_type.split(",")]
            else:
                # self.memory_type = ["sys_event_v1", "event_v1"]
                self.memory_type = ["sys_event_v1", "sys_profile_v1"]

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
            client.get_collection(
                collection_name=self.index, project=self.volcengine_project
            )
            logger.info(f"Collection {self.index} exist.")
            return True
        except Exception:
            logger.info(f"Collection {self.index} not exist.")
            return False

    def _create_collection(self) -> None:
        logger.info(
            f"Create collection with collection_name={self.index}, builtin_event_types={self.memory_type}"
        )
        client = self._get_client()
        response = client.create_collection(
            collection_name=self.index,
            project=self.volcengine_project,
            description="Created by Volcengine Agent Development Kit VeADK",
            builtin_event_types=self.memory_type,
        )
        logger.debug(f"Create collection with response {response}")
        return response

    def _get_ak_sk_sts(self) -> tuple[str, str, str]:
        ak = ""
        sk = ""
        sts_token = ""

        if self.volcengine_access_key and self.volcengine_secret_key:
            ak = self.volcengine_access_key
            sk = self.volcengine_secret_key
            sts_token = self.session_token
            logger.debug(
                "Get volcengine credential from Environments for VikingMEMBackend"
            )

        else:
            cred = get_credential_from_vefaas_iam()
            ak = cred.access_key_id
            sk = cred.secret_access_key
            sts_token = cred.session_token
            logger.debug(
                "Get volcengine credential from VeFaaS IAM file for VikingMEMBackend."
            )

        return ak, sk, sts_token

    def _get_client(self) -> VikingDBMemoryClient:
        ak, sk, sts_token = self._get_ak_sk_sts()
        if self.cloud_provider.lower() == "byteplus":
            host = f"api-knowledgebase.mlp.{self.region}.bytepluses.com"

        logger.info(f"Cloud provider: {self.cloud_provider.lower()}")
        logger.info(f"VikingDBLTMBackend: region={self.region}, host={host}")

        return VikingDBMemoryClient(
            host=host,
            ak=ak,
            sk=sk,
            sts_token=sts_token,
            region=self.region,
        )

    def _get_sdk_client(self) -> VikingMem:
        ak, sk, sts_token = self._get_ak_sk_sts()
        if self.cloud_provider.lower() == "byteplus":
            host = f"api-knowledgebase.mlp.{self.region}.bytepluses.com"

        logger.info(f"Cloud provider: {self.cloud_provider.lower()}")
        logger.info(f"VikingDBLTMBackend: region={self.region}, host={host}")

        client = VikingDBMemoryClient(
            host=host,
            region=self.region,
            ak=ak,
            sk=sk,
            sts_token=sts_token,
        )

        return VikingMem(
            host=client.get_host(),
            region=self.region,
            auth=IAM(
                ak=ak,
                sk=sk,
            ),
            sts_token=sts_token,
        )

    @override
    def save_memory(
        self,
        user_id: str,
        event_strings: list[str],
        **kwargs,
    ) -> bool:
        assistant_id = kwargs.get("assistant_id", "assistant")
        session_id = kwargs.get("session_id", str(uuid.uuid1()))
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
            "default_assistant_id": assistant_id,
            "time": int(time.time() * 1000),
        }

        logger.debug(
            f"Request for add {len(messages)} memory to VikingDB: collection_name={self.index}, metadata={metadata}, session_id={session_id}, messages={messages}"
        )

        client = self._get_sdk_client()
        collection = client.get_collection(
            collection_name=self.index, project_name=self.volcengine_project
        )
        response = collection.add_session(
            session_id=session_id,
            messages=messages,
            metadata=metadata,
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

        client = self._get_sdk_client()
        collection = client.get_collection(
            collection_name=self.index, project_name=self.volcengine_project
        )
        response = collection.search_memory(
            query=query,
            filter=filter,
            limit=top_k,
        )

        logger.debug(f"Response from search memory in VikingDB: {response}")

        if not response.get("code") == 0:
            raise ValueError(f"Search VikingDB memory error: {response}")

        logger.debug(f"Original response from Viking Memory: {response}")

        result = response.get("data", {}).get("result_list", [])

        return (
            [
                json.dumps(
                    {"role": "user", "parts": [{"text": str(result)}]},
                    ensure_ascii=False,
                )
            ]
            if result
            else []
        )

    def get_user_profile(self, user_id: str) -> str:
        from veadk.utils.volcengine_sign import ve_request

        response: dict = self._get_client().get_collection(
            collection_name=self.index, project=self.volcengine_project
        )

        mem_id = response["Result"]["ResourceId"]
        logger.info(
            f"Get user profile for user_id={user_id} from Viking Memory with mem_id={mem_id}"
        )

        ak, sk, sts_token = self._get_ak_sk_sts()
        response = ve_request(
            request_body={
                "filter": {
                    "user_id": [user_id],
                    "memory_category": 1,
                },
                "limit": 5000,
                "resource_id": mem_id,
            },
            action="MemorySearch",
            ak=ak,
            sk=sk,
            header={"X-Security-Token": sts_token},
            service="vikingdb",
            version="2025-06-09",
            region=self.region,
            host="open.volcengineapi.com",
        )

        try:
            logger.debug(
                f"Response from VikingDB: {response}, user_profile: {response['data']['result_list'][0]['memory_info']['user_profile']}"
            )
            return response["data"]["result_list"][0]["memory_info"]["user_profile"]
        except (KeyError, IndexError):
            logger.error(
                f"Failed to get user profile for user_id={user_id} mem_id={mem_id}: {response}"
            )
            return ""
