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

import os

from typing_extensions import override

from veadk.auth.veauth.base_veauth import BaseVeAuth
from veadk.utils.logger import get_logger
from veadk.utils.volcengine_sign import ve_request

logger = get_logger(__name__)


class APMPlusVeAuth(BaseVeAuth):
    def __init__(
        self,
        access_key: str = os.getenv("VOLCENGINE_ACCESS_KEY", ""),
        secret_key: str = os.getenv("VOLCENGINE_SECRET_KEY", ""),
    ) -> None:
        super().__init__(access_key, secret_key)

        self._token: str = ""

    @override
    def _fetch_token(self) -> None:
        logger.info("Fetching APMPlus token...")

        res = ve_request(
            request_body={},
            action="GetAppKey",
            ak=self.access_key,
            sk=self.secret_key,
            service="apmplus_server",
            version="2024-07-30",
            region="cn-beijing",
            host="open.volcengineapi.com",
        )
        try:
            self._token = res["data"]["app_key"]
        except KeyError:
            raise ValueError(f"Failed to get APMPlus token: {res}")

    @property
    def token(self) -> str:
        if self._token:
            return self._token
        self._fetch_token()
        return self._token
