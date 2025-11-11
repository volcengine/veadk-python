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

import volcenginesdkcore
from volcenginesdkid import IDApi


class Identity:
    def __init__(self, access_key: str, secret_key: str, region: str = "cn-beijing"):
        self.ak = access_key
        self.sk = secret_key
        self.region = region
        configuration = volcenginesdkcore.Configuration()
        configuration.ak = self.ak
        configuration.sk = self.sk
        configuration.region = region

        self.api_client = volcenginesdkcore.ApiClient(configuration=configuration)
        self.identity_client = IDApi(api_client=self.api_client)

    def create_user_pool(self, name: str) -> str:
        from volcenginesdkid import CreateUserPoolRequest

        request = CreateUserPoolRequest(
            name=name,
        )
        thread = self.identity_client.create_user_pool(request, async_req=True)
        result = thread.get()
        return result.to_dict()["uid"]

    def get_user_pool(self, name: str) -> str | None:
        from volcenginesdkid import (
            ListUserPoolsRequest,
            FilterForListUserPoolsInput,
        )

        request = ListUserPoolsRequest(
            page_number=1,
            page_size=1,
            filter=FilterForListUserPoolsInput(
                name=name,
            ),
        )
        thread = self.identity_client.list_user_pools(request, async_req=True)
        result = thread.get().to_dict()
        if result["total_count"] == 0:
            return None
        return result["data"][0]["uid"]

    def create_user_pool_client(
        self, user_pool_uid: str, name: str, client_type: str
    ) -> tuple[str, str]:
        from volcenginesdkid import CreateUserPoolClientRequest

        request = CreateUserPoolClientRequest(
            user_pool_uid=user_pool_uid,
            name=name,
            client_type=client_type,
        )
        thread = self.identity_client.create_user_pool_client(request, async_req=True)
        result = thread.get().to_dict()
        return result["uid"], result["client_secret"]

    def register_callback_for_user_pool_client(
        self,
        user_pool_uid: str,
        client_uid: str,
        callback_url: str,
        web_origin: str,
    ):
        from volcenginesdkid import (
            GetUserPoolClientRequest,
            UpdateUserPoolClientRequest,
        )

        request = GetUserPoolClientRequest(
            user_pool_uid=user_pool_uid,
            client_uid=client_uid,
        )
        thread = self.identity_client.get_user_pool_client(request, async_req=True)
        result = thread.get().to_dict()

        allowed_callback_urls = result["allowed_callback_urls"]
        if not allowed_callback_urls:
            allowed_callback_urls = []
        allowed_callback_urls.append(callback_url)
        allowed_web_origins = result["allowed_web_origins"]
        if not allowed_web_origins:
            allowed_web_origins = []
        allowed_web_origins.append(web_origin)

        request2 = UpdateUserPoolClientRequest(
            user_pool_uid=user_pool_uid,
            client_uid=client_uid,
            name=result["name"],
            description=result["description"],
            allowed_callback_urls=allowed_callback_urls,
            allowed_logout_urls=result["allowed_logout_urls"],
            allowed_web_origins=allowed_web_origins,
            allowed_cors=result["allowed_cors"],
            id_token=result["id_token"],
            refresh_token=result["refresh_token"],
        )
        thread2 = self.identity_client.update_user_pool_client(request2, async_req=True)
        thread2.get()

    def get_user_pool_client(
        self, user_pool_uid: str, name: str
    ) -> tuple[str, str] | None:
        from volcenginesdkid import (
            ListUserPoolClientsRequest,
            FilterForListUserPoolClientsInput,
            GetUserPoolClientRequest,
        )

        request = ListUserPoolClientsRequest(
            user_pool_uid=user_pool_uid,
            page_number=1,
            page_size=1,
            filter=FilterForListUserPoolClientsInput(
                name=name,
            ),
        )
        thread = self.identity_client.list_user_pool_clients(request, async_req=True)
        result = thread.get().to_dict()
        if result["total_count"] == 0:
            return None

        client_uid = result["data"][0]["uid"]
        request2 = GetUserPoolClientRequest(
            user_pool_uid=user_pool_uid, client_uid=client_uid
        )
        thread2 = self.identity_client.get_user_pool_client(request2, async_req=True)
        result2 = thread2.get()
        return client_uid, result2.to_dict()["client_secret"]
