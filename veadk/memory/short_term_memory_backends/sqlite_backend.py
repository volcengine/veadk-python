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
import sqlite3
from functools import cached_property
from typing import Any

from google.adk import version as adk_version
from google.adk.sessions import (
    BaseSessionService,
    DatabaseSessionService,
)
from packaging.version import parse as parse_version
from typing_extensions import override

from veadk.memory.short_term_memory_backends.base_backend import (
    BaseShortTermMemoryBackend,
)


class SQLiteSTMBackend(BaseShortTermMemoryBackend):
    local_path: str

    def model_post_init(self, context: Any) -> None:
        self.local_path = os.path.abspath(self.local_path)
        # if the DB file not exists, create it
        if not self._db_exists():
            os.makedirs(os.path.dirname(self.local_path), exist_ok=True)
            conn = sqlite3.connect(self.local_path)
            conn.close()

        if parse_version(adk_version.__version__) < parse_version("1.19.0"):
            self._db_url = f"sqlite:///{self.local_path}"
        else:
            self._db_url = f"sqlite+aiosqlite:///{self.local_path}"

    @cached_property
    @override
    def session_service(self) -> BaseSessionService:
        return DatabaseSessionService(db_url=self._db_url)

    def _db_exists(self) -> bool:
        return os.path.exists(self.local_path)
