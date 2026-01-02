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
    Session,
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
from veadk.models.ark_llm import build_cache_metadata
from veadk.utils.logger import get_logger

logger = get_logger(__name__)


def wrap_get_session_with_callbacks(obj, callback_fn: Callable):
    get_session_fn = getattr(obj, "get_session")

    @wraps(get_session_fn)
    async def wrapper(*args, **kwargs):
        result = await get_session_fn(*args, **kwargs)
        callback_fn(result, *args, **kwargs)
        return result

    setattr(obj, "get_session", wrapper)


def enable_responses_api_for_session_service(result, *args, **kwargs):
    if result and isinstance(result, Session):
        if result.events:
            for event in result.events:
                if (
                    event.actions
                    and event.actions.state_delta
                    and not event.cache_metadata
                    and "response_id" in event.actions.state_delta
                ):
                    event.cache_metadata = build_cache_metadata(
                        response_id=event.actions.state_delta.get("response_id"),
                    )


class ShortTermMemory(BaseModel):
    """Short term memory for agent execution.

    The short term memory represents the context of the agent model. All content in the short term memory will be sent to agent model directly, including the system prompt, historical user prompt, and historical model responses.

    Attributes:
        backend (Literal["local", "mysql", "sqlite", "postgresql", "database"]):
            The backend of short term memory:
            - `local` for in-memory storage
            - `mysql` for mysql / PostgreSQL storage
            - `sqlite` for locally sqlite storage
        backend_configs (dict): Configuration dict for init short term memory backend.
        db_url (str):
            Database connection url for init short term memory backend.
            For example, `sqlite:///./test.db`. Once set, it will override the `backend` parameter.
        local_database_path (str):
            Local database path, only used when `backend` is `sqlite`.
            Default to `/tmp/veadk_local_database.db`.
        after_load_memory_callback (Callable | None):
            A callback to be called after loading memory from the backend. The callback function should accept `Session` as an input.

    Examples:
        ### In-memory simple memory

        You can initialize a short term memory with in-memory storage:

        ```python
        from veadk import Agent, Runner
        from veadk.memory.short_term_memory import ShortTermMemory
        import asyncio

        session_id = "veadk_playground_session"

        agent = Agent()
        short_term_memory = ShortTermMemory(backend="local")

        runner = Runner(
            agent=agent, short_term_memory=short_term_memory)

        # This invocation will be stored in short-term memory
        response = asyncio.run(runner.run(
            messages="My name is VeADK", session_id=session_id
        ))
        print(response)

        # The history invocation can be fetched by model
        response = asyncio.run(runner.run(
            messages="Do you remember my name?", session_id=session_id # keep the same `session_id`
        ))
        print(response)
        ```

        ### Memory with a Database URL

        Also you can use a databasae connection URL to initialize a short-term memory:

        ```python
        from veadk.memory.short_term_memory import ShortTermMemory

        short_term_memory = ShortTermMemory(db_url="...")
        ```

        ### Memory with SQLite

        Once you want to start the short term memory with a local SQLite, you can specify the backend to `sqlite`. It will create a local database in `local_database_path`:

        ```python
        from veadk.memory.short_term_memory import ShortTermMemory

        short_term_memory = ShortTermMemory(backend="sqlite", local_database_path="")
        ```
    """

    backend: Literal["local", "mysql", "sqlite", "postgresql", "database"] = "local"

    backend_configs: dict = Field(default_factory=dict)

    db_kwargs: dict = Field(default_factory=dict)

    db_url: str = ""

    local_database_path: str = "/tmp/veadk_local_database.db"

    after_load_memory_callback: Callable | None = None

    _session_service: BaseSessionService = PrivateAttr()

    def model_post_init(self, __context: Any) -> None:
        if self.db_url:
            logger.info("The `db_url` is set, ignore `backend` option.")
            if self.db_url.count("@") > 1 or self.db_url.count(":") > 2:
                logger.warning(
                    "Multiple `@` or `:` symbols detected in the database URL. "
                    "Please encode `username` or `password` with `urllib.parse.quote_plus`. "
                    "Examples: p@ssword→p%40ssword."
                )
            self._session_service = DatabaseSessionService(
                db_url=self.db_url, **self.db_kwargs
            )
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
                        db_kwargs=self.db_kwargs, **self.backend_configs
                    ).session_service
                case "sqlite":
                    self._session_service = SQLiteSTMBackend(
                        local_path=self.local_database_path
                    ).session_service
                case "postgresql":
                    self._session_service = PostgreSqlSTMBackend(
                        db_kwargs=self.db_kwargs, **self.backend_configs
                    ).session_service

        if self.backend != "local":
            wrap_get_session_with_callbacks(
                self._session_service, enable_responses_api_for_session_service
            )

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
    ) -> Session | None:
        """Create or retrieve a user session.

        Short term memory can attempt to create a new session for a given application and user. If a session with the same `session_id` already exists, it will be returned instead of creating a new one.

        If the underlying session service is backed by a database (`DatabaseSessionService`), the method first lists all existing sessions for the given `app_name` and `user_id` and logs the number of sessions found. It then checks whether a session with the specified `session_id` already exists:
        - If it exists → returns the existing session.
        - If it does not exist → creates and returns a new session.

        Args:
            app_name (str): The name of the application associated with the session.
            user_id (str): The unique identifier of the user.
            session_id (str): The unique identifier of the session to be created or retrieved.

        Returns:
            Session | None: The retrieved or newly created `Session` object, or `None` if the session creation failed.

        Examples:
            Create a new session manually:

            ```python
            import asyncio

            from veadk.memory import ShortTermMemory

            app_name = "app_name"
            user_id = "user_id"
            session_id = "session_id"

            short_term_memory = ShortTermMemory()

            session = asyncio.run(
                short_term_memory.create_session(
                    app_name=app_name, user_id=user_id, session_id=session_id
                )
            )

            print(session)

            session = asyncio.run(
                short_term_memory.session_service.get_session(
                    app_name=app_name, user_id=user_id, session_id=session_id
                )
            )

            print(session)
            ```
        """
        if isinstance(self._session_service, DatabaseSessionService):
            list_sessions_response = await self._session_service.list_sessions(
                app_name=app_name, user_id=user_id
            )

            logger.debug(
                f"Loaded {len(list_sessions_response.sessions)} sessions from db {self.db_url}."
            )

        session = await self._session_service.get_session(
            app_name=app_name, user_id=user_id, session_id=session_id
        )

        if session:
            logger.info(
                f"Session {session_id} already exists with app_name={app_name} user_id={user_id}."
            )
            return session
        else:
            return await self._session_service.create_session(
                app_name=app_name, user_id=user_id, session_id=session_id
            )
