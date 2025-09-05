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
from typing import Type

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


def veauth(auth_token_name: str, auth_cls: Type[BaseVeAuth]):
    def decorator(cls: Type):
        # api_key -> _api_key
        # for cache
        private_auth_token_name = f"_{auth_token_name}"
        setattr(cls, private_auth_token_name, "")

        # init a auth cls for fetching token
        auth_cls_instance = "_auth_cls_instance"
        setattr(cls, auth_cls_instance, auth_cls())

        def getattribute(self, name: str):
            if name != auth_token_name:
                return object.__getattribute__(self, name)
            if name == auth_token_name:
                token = object.__getattribute__(self, name)

                if token:
                    return token
                elif not token and not getattr(cls, private_auth_token_name):
                    token = getattr(cls, auth_cls_instance).token
                    setattr(cls, private_auth_token_name, token)
                    return token
                elif not token and getattr(cls, private_auth_token_name):
                    return getattr(cls, private_auth_token_name)
            return token

        setattr(cls, "__getattribute__", getattribute)
        return cls

    return decorator
