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
from abc import ABC, abstractmethod

from veadk.auth.base_auth import BaseAuth


class BaseVeAuth(ABC, BaseAuth):
    volcengine_access_key: str
    """Volcengine Access Key"""

    volcengine_secret_key: str
    """Volcengine Secret Key"""

    def __init__(
        self,
        access_key: str | None = None,
        secret_key: str | None = None,
    ) -> None:
        super().__init__()

        final_ak = access_key or os.getenv("VOLCENGINE_ACCESS_KEY")
        final_sk = secret_key or os.getenv("VOLCENGINE_SECRET_KEY")

        assert final_ak, "Volcengine access key cannot be empty."
        assert final_sk, "Volcengine secret key cannot be empty."

        self.access_key = final_ak
        self.secret_key = final_sk

        self._token: str = ""

    @abstractmethod
    def _fetch_token(self) -> None: ...

    @property
    def token(self) -> str: ...
