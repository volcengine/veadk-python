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
import threading
from veadk.utils.misc import getenv
from volcengine.ApiInfo import ApiInfo
from volcengine.auth.SignerV4 import SignerV4
from volcengine.base.Service import Service
from volcengine.Credentials import Credentials
from volcengine.ServiceInfo import ServiceInfo


class VikingDBMemoryException(Exception):
    def __init__(self, code, request_id, message=None):
        self.code = code
        self.request_id = request_id
        self.message = "{}, code:{}，request_id:{}".format(
            message, self.code, self.request_id
        )

    def __str__(self):
        return self.message


class VikingDBMemoryClient(Service):
    _instance_lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if not hasattr(VikingDBMemoryClient, "_instance"):
            with VikingDBMemoryClient._instance_lock:
                if not hasattr(VikingDBMemoryClient, "_instance"):
                    VikingDBMemoryClient._instance = object.__new__(cls)
        return VikingDBMemoryClient._instance

    def __init__(
        self,
        host="api-knowledgebase.mlp.cn-beijing.volces.com",
        region="cn-beijing",
        ak="",
        sk="",
        sts_token="",
        scheme="https",
        connection_timeout=30,
        socket_timeout=30,
    ):
        env_host = getenv(
            "DATABASE_VIKINGMEM_BASE_URL", default_value=None, allow_false_values=True
        )
        if env_host:
            if env_host.startswith("http://"):
                host = env_host.replace("http://", "")
                scheme = "http"
            elif env_host.startswith("https://"):
                host = env_host.replace("https://", "")
                scheme = "https"
            else:
                raise ValueError(
                    "DATABASE_VIKINGMEM_BASE_URL must start with http:// or https://"
                )

        self.service_info = VikingDBMemoryClient.get_service_info(
            host, region, scheme, connection_timeout, socket_timeout
        )
        self.api_info = VikingDBMemoryClient.get_api_info()
        super(VikingDBMemoryClient, self).__init__(self.service_info, self.api_info)
        if ak:
            self.set_ak(ak)
        if sk:
            self.set_sk(sk)
        if sts_token:
            self.set_session_token(session_token=sts_token)
        try:
            self.get_body("Ping", {}, json.dumps({}))
        except Exception as e:
            raise VikingDBMemoryException(
                1000028, "missed", "host or region is incorrect: {}".format(str(e))
            ) from None

    def setHeader(self, header):
        api_info = VikingDBMemoryClient.get_api_info()
        for key in api_info:
            for item in header:
                api_info[key].header[item] = header[item]
        self.api_info = api_info

    def get_host(self):
        return self.service_info.host

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
            except Exception as e:
                raise VikingDBMemoryException(
                    1000028, "missed", "json load res error, res:{}".format(str(e))
                ) from None
            code = res_json.get("code", 1000028)
            request_id = res_json.get("request_id", 1000028)
            message = res_json.get("message", None)

            raise VikingDBMemoryException(code, request_id, message)

        if res == "":
            raise VikingDBMemoryException(
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
            except Exception as e:
                raise VikingDBMemoryException(
                    1000028, "missed", "json load res error, res:{}".format(str(e))
                ) from None
            code = res_json.get("code", 1000028)
            request_id = res_json.get("request_id", 1000028)
            message = res_json.get("message", None)
            raise VikingDBMemoryException(code, request_id, message)
        if res == "":
            raise VikingDBMemoryException(
                1000028,
                "missed",
                "empty response due to unknown error, please contact customer service",
            ) from None
        return res

    def create_collection(
        self,
        collection_name,
        description="",
        custom_event_type_schemas=[],
        custom_entity_type_schemas=[],
        builtin_event_types=[],
        builtin_entity_types=[],
    ):
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