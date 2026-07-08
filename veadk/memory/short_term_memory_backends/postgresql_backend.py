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

import asyncio
import concurrent.futures
import re
from functools import cached_property
from typing import Any
from urllib.parse import quote_plus

from google.adk.sessions import (
    BaseSessionService,
    DatabaseSessionService,
)
from pydantic import Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from typing_extensions import override

import veadk.config  # noqa E401
from veadk.configs.database_configs import PostgreSqlConfig
from veadk.memory.short_term_memory_backends.base_backend import (
    BaseShortTermMemoryBackend,
)
from veadk.utils.adk_compat import should_use_async_db_drivers
from veadk.utils.logger import get_logger

logger = get_logger(__name__)

# A conservative, injection-safe schema identifier: letters, digits, underscore,
# not starting with a digit. It is interpolated into DDL, so it must be validated.
_SCHEMA_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _validate_schema(schema: str) -> None:
    if not _SCHEMA_RE.match(schema):
        raise ValueError(
            f"Invalid PostgreSQL schema name '{schema}'. Allowed: letters, "
            "digits, underscore; must not start with a digit."
        )


def _with_search_path(db_kwargs: dict, schema: str) -> dict:
    """Return db_kwargs with the connection's search_path pinned to `schema` via
    the asyncpg startup parameter (reliable; unlike a per-statement ``SET`` in a
    connect listener, which asyncpg does not persist). Existing connect_args are
    preserved."""
    kwargs = dict(db_kwargs)
    connect_args = dict(kwargs.get("connect_args", {}))
    server_settings = dict(connect_args.get("server_settings", {}))
    server_settings["search_path"] = schema
    connect_args["server_settings"] = server_settings
    kwargs["connect_args"] = connect_args
    return kwargs


async def _acreate_schema(db_url: str, schema: str) -> None:
    # Use a throwaway engine so the real session-service engine is never bound to
    # this temporary event loop. CREATE SCHEMA is schema-qualified, so it works
    # regardless of search_path.
    engine = create_async_engine(db_url)
    try:
        async with engine.begin() as conn:
            await conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
    finally:
        await engine.dispose()


def _ensure_schema(db_url: str, schema: str) -> None:
    """Create `schema` if absent, before ADK's lazy ``create_all`` runs, so the
    session tables are created inside it. Safe to call from sync or async
    context."""
    try:
        asyncio.get_running_loop()
        running = True
    except RuntimeError:
        running = False
    if running:
        # A loop is already running here; run the coroutine on its own loop in a
        # worker thread so we don't touch the caller's loop.
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            executor.submit(
                lambda: asyncio.run(_acreate_schema(db_url, schema))
            ).result()
    else:
        asyncio.run(_acreate_schema(db_url, schema))


class PostgreSqlSTMBackend(BaseShortTermMemoryBackend):
    postgresql_config: PostgreSqlConfig = Field(default_factory=PostgreSqlConfig)
    db_kwargs: dict = Field(default_factory=dict)

    def model_post_init(self, context: Any) -> None:
        encoded_username = quote_plus(self.postgresql_config.user)
        encoded_password = quote_plus(self.postgresql_config.password)
        if should_use_async_db_drivers():
            self._db_url = f"postgresql+asyncpg://{encoded_username}:{encoded_password}@{self.postgresql_config.host}:{self.postgresql_config.port}/{self.postgresql_config.database}"
        else:
            self._db_url = f"postgresql://{encoded_username}:{encoded_password}@{self.postgresql_config.host}:{self.postgresql_config.port}/{self.postgresql_config.database}"

    @cached_property
    @override
    def session_service(self) -> BaseSessionService:
        schema = self.postgresql_config.schema
        if not schema:
            return DatabaseSessionService(db_url=self._db_url, **self.db_kwargs)

        _validate_schema(schema)
        # 1) make sure the schema exists, then 2) pin every connection to it.
        _ensure_schema(self._db_url, schema)
        db_kwargs = _with_search_path(self.db_kwargs, schema)
        logger.info(f"Short-term memory isolated in PostgreSQL schema '{schema}'.")
        return DatabaseSessionService(db_url=self._db_url, **db_kwargs)
