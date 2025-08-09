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
import random
import string
import threading
import time
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field
from volcengine.ApiInfo import ApiInfo
from volcengine.auth.SignerV4 import SignerV4
from volcengine.base.Service import Service
from volcengine.Credentials import Credentials
from volcengine.ServiceInfo import ServiceInfo

from veadk.config import getenv
from veadk.database.base_database import BaseDatabase
from veadk.utils.logger import get_logger

logger = get_logger(__name__)


class VikingMemConfig(BaseModel):
    volcengine_ak: Optional[str] = Field(
        default=getenv("VOLCENGINE_ACCESS_KEY"),
        description="VikingDB access key",
    )
    volcengine_sk: Optional[str] = Field(
        default=getenv("VOLCENGINE_SECRET_KEY"),
        description="VikingDB secret key",
    )
    project: Optional[str] = Field(
        default=getenv("DATABASE_VIKING_PROJECT"),
        description="VikingDB project name",
    )
    region: Optional[str] = Field(
        default=getenv("DATABASE_VIKING_REGION"),
        description="VikingDB region",
    )


# ======= adapted from https://github.com/volcengine/mcp-server/blob/main/server/mcp_server_vikingdb_memory/src/mcp_server_vikingdb_memory/common/memory_client.py =======
class VikingMemoryException(Exception):
    def __init__(self, code, request_id, message=None):
        self.code = code
        self.request_id = request_id
        self.message = "{}, code:{}，request_id:{}".format(
            message, self.code, self.request_id
        )

    def __str__(self):
        return self.message


class VikingMemoryService(Service):
    _instance_lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if not hasattr(VikingMemoryService, "_instance"):
            with VikingMemoryService._instance_lock:
                if not hasattr(VikingMemoryService, "_instance"):
                    VikingMemoryService._instance = object.__new__(cls)
        return VikingMemoryService._instance

    def __init__(
        self,
        host="api-knowledgebase.mlp.cn-beijing.volces.com",
        region="cn-beijing",
        ak="",
        sk="",
        sts_token="",
        scheme="http",
        connection_timeout=30,
        socket_timeout=30,
    ):
        self.service_info = VikingMemoryService.get_service_info(
            host, region, scheme, connection_timeout, socket_timeout
        )
        self.api_info = VikingMemoryService.get_api_info()
        super(VikingMemoryService, self).__init__(self.service_info, self.api_info)
        if ak:
            self.set_ak(ak)
        if sk:
            self.set_sk(sk)
        if sts_token:
            self.set_session_token(session_token=sts_token)
        try:
            self.get_body("Ping", {}, json.dumps({}))
        except Exception as e:
            raise VikingMemoryException(
                1000028, "missed", "host or region is incorrect: {}".format(str(e))
            ) from None

    def setHeader(self, header):
        api_info = VikingMemoryService.get_api_info()
        for key in api_info:
            for item in header:
                api_info[key].header[item] = header[item]
        self.api_info = api_info

    @staticmethod
    def get_service_info(host, region, scheme, connection_timeout, socket_timeout):
        service_info = ServiceInfo(
            host,
            {"Host": host},
            Credentials("", "", "air", region),
            connection_timeout,
            socket_timeout,
            scheme=scheme,
        )
        return service_info

    @staticmethod
    def get_api_info():
        api_info = {
            "CreateCollection": ApiInfo(
                "POST",
                "/api/memory/collection/create",
                {},
                {},
                {"Accept": "application/json", "Content-Type": "application/json"},
            ),
            "GetCollection": ApiInfo(
                "POST",
                "/api/memory/collection/info",
                {},
                {},
                {"Accept": "application/json", "Content-Type": "application/json"},
            ),
            "DropCollection": ApiInfo(
                "POST",
                "/api/memory/collection/delete",
                {},
                {},
                {"Accept": "application/json", "Content-Type": "application/json"},
            ),
            "UpdateCollection": ApiInfo(
                "POST",
                "/api/memory/collection/update",
                {},
                {},
                {"Accept": "application/json", "Content-Type": "application/json"},
            ),
            "SearchMemory": ApiInfo(
                "POST",
                "/api/memory/search",
                {},
                {},
                {"Accept": "application/json", "Content-Type": "application/json"},
            ),
            "AddMessages": ApiInfo(
                "POST",
                "/api/memory/messages/add",
                {},
                {},
                {"Accept": "application/json", "Content-Type": "application/json"},
            ),
            "Ping": ApiInfo(
                "GET",
                "/api/memory/ping",
                {},
                {},
                {"Accept": "application/json", "Content-Type": "application/json"},
            ),
        }
        return api_info

    def get_body(self, api, params, body):
        if api not in self.api_info:
            raise Exception("no such api")
        api_info = self.api_info[api]
        r = self.prepare_request(api_info, params)
        r.headers["Content-Type"] = "application/json"
        r.headers["Traffic-Source"] = "SDK"
        r.body = body

        SignerV4.sign(r, self.service_info.credentials)

        url = r.build()
        resp = self.session.get(
            url,
            headers=r.headers,
            data=r.body,
            timeout=(
                self.service_info.connection_timeout,
                self.service_info.socket_timeout,
            ),
        )
        if resp.status_code == 200:
            return json.dumps(resp.json())
        else:
            raise Exception(resp.text.encode("utf-8"))

    def get_body_exception(self, api, params, body):
        try:
            res = self.get_body(api, params, body)
        except Exception as e:
            try:
                res_json = json.loads(e.args[0].decode("utf-8"))
            except Exception:
                raise VikingMemoryException(
                    1000028, "missed", "json load res error, res:{}".format(str(e))
                ) from None
            code = res_json.get("code", 1000028)
            request_id = res_json.get("request_id", 1000028)
            message = res_json.get("message", None)

            raise VikingMemoryException(code, request_id, message)

        if res == "":
            raise VikingMemoryException(
                1000028,
                "missed",
                "empty response due to unknown error, please contact customer service",
            ) from None
        return res

    def get_exception(self, api, params):
        try:
            res = self.get(api, params)
        except Exception as e:
            try:
                res_json = json.loads(e.args[0].decode("utf-8"))
            except Exception:
                raise VikingMemoryException(
                    1000028, "missed", "json load res error, res:{}".format(str(e))
                ) from None
            code = res_json.get("code", 1000028)
            request_id = res_json.get("request_id", 1000028)
            message = res_json.get("message", None)
            raise VikingMemoryException(code, request_id, message)
        if res == "":
            raise VikingMemoryException(
                1000028,
                "missed",
                "empty response due to unknown error, please contact customer service",
            ) from None
        return res

    def create_collection(
        self,
        collection_name,
        description="",
        custom_event_type_schemas=None,
        custom_entity_type_schemas=None,
        builtin_event_types=None,
        builtin_entity_types=None,
    ):
        if custom_event_type_schemas is None:
            custom_event_type_schemas = []
        if custom_entity_type_schemas is None:
            custom_entity_type_schemas = []
        if builtin_entity_types is None:
            builtin_entity_types = ["sys_profile_v1"]
        if builtin_event_types is None:
            builtin_event_types = ["sys_event_v1", "sys_profile_collect_v1"]
        params = {
            "CollectionName": collection_name,
            "Description": description,
            "CustomEventTypeSchemas": custom_event_type_schemas,
            "CustomEntityTypeSchemas": custom_entity_type_schemas,
            "BuiltinEventTypes": builtin_event_types,
            "BuiltinEntityTypes": builtin_entity_types,
        }
        res = self.json("CreateCollection", {}, json.dumps(params))
        return json.loads(res)

    def get_collection(self, collection_name):
        params = {"CollectionName": collection_name}
        res = self.json("GetCollection", {}, json.dumps(params))
        return json.loads(res)

    def drop_collection(self, collection_name):
        params = {"CollectionName": collection_name}
        res = self.json("DropCollection", {}, json.dumps(params))
        return json.loads(res)

    def update_collection(
        self,
        collection_name,
        custom_event_type_schemas=[],
        custom_entity_type_schemas=[],
        builtin_event_types=[],
        builtin_entity_types=[],
    ):
        params = {
            "CollectionName": collection_name,
            "CustomEventTypeSchemas": custom_event_type_schemas,
            "CustomEntityTypeSchemas": custom_entity_type_schemas,
            "BuiltinEventTypes": builtin_event_types,
            "BuiltinEntityTypes": builtin_entity_types,
        }
        res = self.json("UpdateCollection", {}, json.dumps(params))
        return json.loads(res)

    def search_memory(self, collection_name, query, filter, limit=10):
        params = {
            "collection_name": collection_name,
            "limit": limit,
            "filter": filter,
        }
        if query:
            params["query"] = query
        res = self.json("SearchMemory", {}, json.dumps(params))
        return json.loads(res)

    def add_messages(
        self, collection_name, session_id, messages, metadata, entities=None
    ):
        params = {
            "collection_name": collection_name,
            "session_id": session_id,
            "messages": messages,
            "metadata": metadata,
        }
        if entities is not None:
            params["entities"] = entities
        res = self.json("AddMessages", {}, json.dumps(params))
        return json.loads(res)


def memory2event(role, text):
    return json.dumps({"role": role, "parts": [{"text": text}]}, ensure_ascii=False)


def generate_random_letters(length):
    # 生成包含所有大小写字母的字符集
    letters = string.ascii_letters
    return "".join(random.choice(letters) for _ in range(length))


def format_milliseconds(timestamp_ms):
    """
    Convert the millisecond - level timestamp to a string in the 'YYYYMMDD HH:MM:SS' format.

    Parameters:
    - timestamp_ms: Millisecond - level timestamp (integer or float)

    Returns:
    - Formatted time string

    """
    # Convert milliseconds to seconds
    timestamp_seconds = timestamp_ms / 1000

    # Convert to a datetime object
    dt = datetime.fromtimestamp(timestamp_seconds)

    # Output in the specified format
    return dt.strftime("%Y%m%d %H:%M:%S")


# ======= adapted from https://github.com/volcengine/mcp-server/blob/main/server/mcp_server_vikingdb_memory/src/mcp_server_vikingdb_memory/common/memory_client.py =======


class VikingMemoryDatabase(BaseModel, BaseDatabase):
    config: VikingMemConfig = Field(
        default_factory=VikingMemConfig,
        description="VikingDB configuration",
    )

    def model_post_init(self, context: Any, /) -> None:
        self._vm = VikingMemoryService(
            ak=self.config.volcengine_ak, sk=self.config.volcengine_sk
        )

    def add_memories(
        self,
        collection_name: str,
        text: str,
        user_id: str,
    ) -> str:
        # Add Messages
        session_id = generate_random_letters(10)
        # proces
        message = json.loads(text)
        content = message["parts"][0]["text"]
        role = (
            "user" if message["role"] == "user" else "assistant"
        )  # field 'role': viking memory only allow 'assistant','system','user',
        messages = [{"role": role, "content": content}]
        metadata = {
            "default_user_id": user_id,
            "default_assistant_id": "assistant",
            "time": int(time.time() * 1000),
        }

        rsp = self._vm.add_messages(
            collection_name=collection_name,
            session_id=session_id,
            messages=messages,
            metadata=metadata,
        )
        return str(rsp)

    def add(self, data: list[str], **kwargs):
        collection_name = kwargs.get("collection_name")
        assert collection_name is not None, "collection_name is required"
        user_id = kwargs.get("user_id")
        assert user_id is not None, "user_id is required"
        try:
            self._vm.get_collection(collection_name=collection_name)
        except Exception:
            self._vm.create_collection(
                collection_name=collection_name,
            )

        for text in data:
            self.add_memories(
                collection_name=collection_name, text=text, user_id=user_id
            )

        return "success"

    def search_memory(
        self, collection_name: str, query: str, user_id: str, top_k: int = 5
    ) -> list[str]:
        """
        Search for stored memories. This method is called whenever a user asks any question.
        If a search yields no results, do not repeat the search within the same conversation.
        The retrieved memories are used to supplement your understanding of the user and to reply to the user's question.
        Args:
             collection_name: viking db collection_name
             query: Any question asked by the user.
        Returns:
            The user's memories related to the query.
        """

        result = []
        try:
            # ------- get profiles -----------
            try:
                limit = 1
                filter = {
                    "user_id": user_id,
                    "memory_type": ["sys_profile_v1"],
                }
                rsp = self._vm.search_memory(
                    collection_name=collection_name,
                    query="sys_profile_v1",
                    filter=filter,
                    limit=limit,
                )
                profiles = [
                    item.get("memory_info").get("user_profile")
                    for item in rsp.get("data").get("result_list")
                ]
                if len(profiles) > 0:
                    result.append(memory2event("user", profiles[0]))
            except Exception as e:
                result.append(
                    memory2event("user", f"SearchMemory: Get Profiles Error: {str(e)}")
                )

            # -------- get memory -----------
            try:
                # Search Memory
                limit = top_k
                filter = {
                    "user_id": user_id,
                    "memory_type": ["sys_event_v1"],
                }
                rsp = self._vm.search_memory(
                    collection_name=collection_name,
                    query=query,
                    filter=filter,
                    limit=limit,
                )
                result_list = rsp.get("data").get("result_list")

                content = [
                    memory2event("user", item.get("memory_info").get("summary"))
                    for item in result_list
                ]

                result.extend(content)

            except Exception as e:
                result.append(
                    memory2event("user", f"SearchMemory: Get Memory Error: {str(e)}")
                )

            return result

        except Exception as e:
            logger.error(f"Error in get_doc: {str(e)}")
            result.append(
                memory2event("user", f"SearchMemory: Get Memory Error: {str(e)}")
            )
            return result

    def query(self, query: str, **kwargs: Any) -> list[str]:
        """
        Args:
            query:  query text
            **kwargs: collection_name(required), top_k(optional, default 5)

        Returns: list of str, the search result
        """
        collection_name = kwargs.get("collection_name")
        assert collection_name is not None, "collection_name is required"
        user_id = kwargs.get("user_id")
        assert user_id is not None, "user_id is required"
        top_k = kwargs.get("top_k", 5)
        resp = self.search_memory(collection_name, query, user_id=user_id, top_k=top_k)
        return resp

    def delete(self, **kwargs: Any):
        collection_name = kwargs.get("collection_name")
        assert collection_name is not None, "collection_name is required"
        self._vm.drop_collection(collection_name)
