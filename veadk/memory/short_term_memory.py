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
from typing import TYPE_CHECKING, Any, Callable, Literal

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
from veadk.utils.logger import get_logger

if TYPE_CHECKING:
    from google.adk.events import Event

    from veadk import Agent

logger = get_logger(__name__)


def wrap_get_session_with_callbacks(obj, callback_fn: Callable):
    get_session_fn = getattr(obj, "get_session")

    @wraps(get_session_fn)
    async def wrapper(*args, **kwargs):
        result = await get_session_fn(*args, **kwargs)
        callback_fn(result, *args, **kwargs)
        return result

    setattr(obj, "get_session", wrapper)


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

    async def generate_profile(
        self,
        app_name: str,
        user_id: str,
        session_id: str,
        events: list["Event"],
    ) -> list[str]:
        import json

        from veadk import Agent, Runner
        from veadk.memory.types import MemoryProfileListV2
        from veadk.utils.misc import write_string_to_file

        event_text = ""
        for event in events:
            event_text += f"- Event id: {event.id}\nEvent content: {event.content}\n"
        print("the events is：\n ", event_text)
        print("-------------------")
        #         instructions_v1 = """Summarize the memory events into at least two groups according to the event content. An event can belong to multiple groups. You must output the summary in JSON format (Each group should have a simple name (only a-z and _ is allowed), and a list of event ids):
        # [
        #     {
        #         "name": "",
        #         "describe":"",
        #         "event_ids": ["Event id here"]
        #     },
        #     {
        #         "name": "",
        #         "describe":"",
        #         "event_ids": ["Event id here"]
        #     }
        # ]
        # The event id must be derived from the provided events data.
        # """
        instructions_v2 = """You are tasked with grouping memory events based on their content. Follow these requirements strictly:

1. **Core Task**: Summarize the provided memory events into at least 2 groups. An event can belong to multiple groups.
2. **Input Specification**: The input is structured memory events data containing unique event IDs (to be used directly in outputs) and event details (characters, time, location, event type, topic, emotion, etc.).
3. **Group Requirements**:
   - **Name**: A concise name for the group, using only lowercase letters and underscores (e.g., "family_dinner_events").
   - **Tags**: A list of entity tags extracted from the events in the group, covering characters, time, location, event type, topic, and emotion (e.g., ["Alice", "2023-10-01", "home", "reunion", "holiday_plans", "joyful"]).
   - **Event IDs**: A list of event IDs from the input data that belong to the group (must match the IDs provided in the input).
4. **Output Format**: Strictly use JSON format with no extra content. The JSON structure must be:
{
    "groups": [
        {
            "name": "group_name_1",
            "tags": ["tag1", "tag2", ...],
            "event_ids": ["event_id_1", "event_id_2", ...]
        },
        {
            "name": "group_name_2",
            "tags": ["tag3", "tag4", ...],
            "event_ids": ["event_id_3", "event_id_4", ...]
        }
    ]
}
5. **Prohibitions**: Do not fabricate event IDs, tags, or group names; all content must be derived from the input events data. Do not output any text outside the JSON structure.
        
"""

        agent = Agent(
            name="memory_summarizer",
            description="A summarizer that summarizes the memory events.",
            instruction=instructions_v2,
            model_name="deepseek-v3-2-251201",
            output_schema=MemoryProfileListV2,
        )
        runner = Runner(agent=agent)
        print("event_text  =", event_text)

        response = await runner.run(messages="Events are: \n" + event_text)
        print("response  =", response)

        # profile path: ./profiles/memory/<app_name>/user_id/session_id/profile_name.json
        try:
            groups = json.loads(response)
            print("groups  =", groups)
        except Exception as e:
            # 捕获所有可能的异常（如JSON解析错误、response未定义、打印异常等）
            print(f"解析JSON时出错: {e}")  # 可选：打印错误信息，便于排查
            groups = {
                "profiles": [],
            }  # 报错时生成空列表

        group_names = [
            {"name": group["name"], "tags": group["tags"]}
            for group in groups["profiles"]
        ]

        for group in groups["profiles"]:
            group["event_list"] = []
            for event_id in group["event_ids"]:
                for event in events:
                    if event.id == event_id:
                        group["event_list"].append(event.content.model_dump_json())

        write_string_to_file(
            content=json.dumps(group_names, ensure_ascii=False),
            file_path=f"./profiles/memory/{app_name}/{user_id}/{session_id}/profile_list.json",
        )

        for group in groups["profiles"]:
            write_string_to_file(
                content=json.dumps(group, ensure_ascii=False),
                file_path=f"./profiles/memory/{app_name}/{user_id}/{session_id}/{group['name']}.json",
            )
        return group_names

    async def compact_history_events(
        self,
        app_name: str,
        user_id: str,
        session_id: str,
        compact_limit: int,
        agent: "Agent",
    ):
        # 1. generate profile
        # 2. compact history events
        # 3. append instruction and corresponding tool
        session = await self.session_service.get_session(
            app_name=app_name, user_id=user_id, session_id=session_id
        )

        compact_event_num = 0
        compact_counter = 0
        for event in session.events:
            if event.content.role == "user":
                compact_counter += 1
                if compact_counter > compact_limit:
                    break
            compact_event_num += 1

        events_need_compact = session.events[:compact_event_num]  # type: ignore

        group_names = await self.generate_profile(
            app_name=app_name,
            user_id=user_id,
            session_id=session_id,
            events=events_need_compact,
        )

        # TODO(yaozheng): directly edit the events are not work as expected,
        # need to check the reason later
        session.events = session.events[compact_event_num:]  # type: ignore
        logger.debug(f"Compacted {compact_event_num} events.")

        agent.instruction += f"""
The session has been compacted for the first {compact_limit} events. The compacted content are divided into following groups:

{group_names}

You can call `load_history_events` to load the compacted events if you need them according to the user's request.
"""

        from veadk.tools.load_history_events import load_history_events

        agent.tools.append(load_history_events)
