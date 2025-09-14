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

from google.adk.sessions import (
    BaseSessionService,
    DatabaseSessionService,
)
from pydantic import Field
from typing_extensions import override

from veadk.configs.database_configs import PostgreSqlConfig
from veadk.memory.short_term_memory_backends.base_backend import (
    BaseShortTermMemoryBackend,
)


class PostgreSqlSTMBackend(BaseShortTermMemoryBackend):
    postgresql_config: PostgreSqlConfig = Field(default_factory=PostgreSqlConfig)

    def model_post_init(self, context: Any) -> None:
        self._db_url = f"postgresql://{self.postgresql_config.user}:{self.postgresql_config.password}@{self.postgresql_config.host}:{self.postgresql_config.port}/{self.postgresql_config.database}"

    @cached_property
    @override
    def session_service(self) -> BaseSessionService:
        return DatabaseSessionService(db_url=self._db_url)
