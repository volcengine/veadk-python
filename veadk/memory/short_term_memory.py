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

from functools import wraps
from typing import Any, Callable, Literal

from google.adk.sessions import (
    BaseSessionService,
    DatabaseSessionService,
    InMemorySessionService,
)
from pydantic import BaseModel, Field, PrivateAttr

from veadk.memory.short_term_memory_backends.mysql_backend import (
    MysqlSTMBackend,
)
from veadk.memory.short_term_memory_backends.postgresql_backend import (
    PostgreSqlSTMBackend,
)
from veadk.memory.short_term_memory_backends.sqlite_backend import (
    SQLiteSTMBackend,
)
from veadk.utils.logger import get_logger

logger = get_logger(__name__)


def wrap_get_session_with_callbacks(obj, callback_fn: Callable):
    get_session_fn = getattr(obj, "get_session")

    @wraps(get_session_fn)
    def wrapper(*args, **kwargs):
        result = get_session_fn(*args, **kwargs)
        callback_fn(result, *args, **kwargs)
        return result

    setattr(obj, "get_session", wrapper)


class ShortTermMemory(BaseModel):
    backend: Literal["local", "mysql", "sqlite", "postgresql", "database"] = "local"
    """Short term memory backend. `Local` for in-memory storage, `mysql` for mysql / PostgreSQL storage. `sqlite` for sqlite storage."""

    backend_configs: dict = Field(default_factory=dict)
    """Backend specific configurations."""

    db_url: str = ""
    """Database connection URL, e.g. `sqlite:///./test.db`. Once set, it will override the `backend` parameter."""

    local_database_path: str = "/tmp/veadk_local_database.db"
    """Local database path, only used when `backend` is `sqlite`. Default to `/tmp/veadk_local_database.db`."""

    after_load_memory_callback: Callable | None = None
    """A callback to be called after loading memory from the backend. The callback function should accept `Session` as an input."""

    _session_service: BaseSessionService = PrivateAttr()

    def model_post_init(self, __context: Any) -> None:
        if self.db_url:
            logger.info("The `db_url` is set, ignore `backend` option.")
            self._session_service = DatabaseSessionService(db_url=self.db_url)
        else:
            if self.backend == "database":
                logger.warning(
                    "Backend `database` is deprecated, use `sqlite` to create short term memory."
                )
                self.backend = "sqlite"
            match self.backend:
                case "local":
                    self._session_service = InMemorySessionService()
                case "mysql":
                    self._session_service = MysqlSTMBackend(
                        **self.backend_configs
                    ).session_service
                case "sqlite":
                    self._session_service = SQLiteSTMBackend(
                        local_path=self.local_database_path
                    ).session_service
                case "postgresql":
                    self._session_service = PostgreSqlSTMBackend(
                        **self.backend_configs
                    ).session_service

        if self.after_load_memory_callback:
            wrap_get_session_with_callbacks(
                self._session_service, self.after_load_memory_callback
            )

    @property
    def session_service(self) -> BaseSessionService:
        return self._session_service

    async def create_session(
        self,
        app_name: str,
        user_id: str,
        session_id: str,
    ) -> None:
        if isinstance(self._session_service, DatabaseSessionService):
            list_sessions_response = await self._session_service.list_sessions(
                app_name=app_name, user_id=user_id
            )

            logger.debug(
                f"Loaded {len(list_sessions_response.sessions)} sessions from db {self.db_url}."
            )

        if (
            await self._session_service.get_session(
                app_name=app_name, user_id=user_id, session_id=session_id
            )
            is None
        ):
            # create a new session for this running
            await self._session_service.create_session(
                app_name=app_name, user_id=user_id, session_id=session_id
            )
