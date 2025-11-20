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

from functools import cached_property
from typing import Any

from google.adk import version as adk_version
from google.adk.sessions import (
    BaseSessionService,
    DatabaseSessionService,
)
from packaging.version import parse as parse_version
from pydantic import Field
from typing_extensions import override
from urllib.parse import quote_plus

import veadk.config  # noqa E401
from veadk.configs.database_configs import MysqlConfig
from veadk.memory.short_term_memory_backends.base_backend import (
    BaseShortTermMemoryBackend,
)


class MysqlSTMBackend(BaseShortTermMemoryBackend):
    mysql_config: MysqlConfig = Field(default_factory=MysqlConfig)

    def model_post_init(self, context: Any) -> None:
        encoded_username = quote_plus(self.mysql_config.user)
        encoded_password = quote_plus(self.mysql_config.password)
        if parse_version(adk_version.__version__) < parse_version("1.19.0"):
            self._db_url = f"mysql+pymysql://{encoded_username}:{encoded_password}@{self.mysql_config.host}/{self.mysql_config.database}"
        else:
            self._db_url = f"mysql+aiomysql://{encoded_username}:{encoded_password}@{self.mysql_config.host}/{self.mysql_config.database}"

    @cached_property
    @override
    def session_service(self) -> BaseSessionService:
        return DatabaseSessionService(db_url=self._db_url)
