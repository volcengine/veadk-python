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

# adapted from Google ADK memory service adk-python/src/google/adk/memory/vertex_ai_memory_bank_service.py at 0a9e67dbca67789247e882d16b139dbdc76a329a · google/adk-python

import ast
import asyncio
import json
from collections.abc import Iterable
from typing import Any, Literal

from google.adk.events.event import Event
from google.adk.memory.base_memory_service import (
    BaseMemoryService,
    SearchMemoryResponse,
)
from google.adk.memory.memory_entry import MemoryEntry
from google.adk.sessions import Session
from google.genai import types
from pydantic import BaseModel, Field
from typing_extensions import Union, override

from veadk.memory.long_term_memory_backends.base_backend import (
    BaseLongTermMemoryBackend,
)
from veadk.utils.logger import get_logger

logger = get_logger(__name__)

MemoryEventType = Literal[
    "text",
    "thought",
    "function_call",
    "function_response",
    "tool_call",
    "tool_response",
    "media",
    "executable_code",
    "code_execution_result",
    "transcription",
    "error",
]
MemoryRole = Literal["user", "assistant", "system"]
MemoryAutoSavePreset = Literal["default", "all", "custom"]


class MemoryAutoSavePolicy(BaseModel):
    """Controls which events automatic long-term-memory saving persists."""

    preset: MemoryAutoSavePreset = "default"
    include_roles: list[MemoryRole] | None = None
    exclude_roles: list[MemoryRole] = Field(default_factory=list)
    include_authors: list[str] | None = None
    exclude_authors: list[str] = Field(default_factory=list)
    include_event_types: list[MemoryEventType] | None = None
    exclude_event_types: list[MemoryEventType] = Field(default_factory=list)
    text_only: bool = True
    include_thought: bool = False
    include_empty_text: bool = False


MemoryAutoSavePolicyInput = Union[
    MemoryAutoSavePolicy,
    Literal["default", "all", "custom"],
    dict[str, Any],
    None,
]


def _get_backend_cls(backend: str) -> type[BaseLongTermMemoryBackend]:
    try:
        match backend:
            case "local":
                from veadk.memory.long_term_memory_backends.in_memory_backend import (
                    InMemoryLTMBackend,
                )

                return InMemoryLTMBackend
            case "opensearch":
                from veadk.memory.long_term_memory_backends.opensearch_backend import (
                    OpensearchLTMBackend,
                )

                return OpensearchLTMBackend
            case "viking":
                from veadk.memory.long_term_memory_backends.vikingdb_memory_backend import (
                    VikingDBLTMBackend,
                )

                return VikingDBLTMBackend
            case "redis":
                from veadk.memory.long_term_memory_backends.redis_backend import (
                    RedisLTMBackend,
                )

                return RedisLTMBackend
            case "mem0":
                from veadk.memory.long_term_memory_backends.mem0_backend import (
                    Mem0LTMBackend,
                )

                return Mem0LTMBackend
            case "openviking":
                from veadk.memory.long_term_memory_backends.openviking_backend import (
                    OpenVikingLTMBackend,
                )

                return OpenVikingLTMBackend
            case "tos_context":
                from veadk.memory.long_term_memory_backends.tos_context_bucket_backend import (
                    TosContextBucketLTMBackend,
                )

                return TosContextBucketLTMBackend
            case _:
                raise ValueError(f"Unsupported long term memory backend: {backend}")
    except ImportError as e:
        if "llama_index" in str(e) or "llama-index" in str(e):
            raise ImportError(
                "LongTermMemory functionality requires 'veadk-python[extensions]'. "
                "Please install it via `pip install veadk-python[extensions]`."
            ) from e
        raise e


class LongTermMemory(BaseMemoryService, BaseModel):
    """Manages long-term memory storage and retrieval for applications.

    This class provides an interface to store, retrieve, and manage long-term
    contextual information using different backend types (e.g., OpenSearch, Redis).
    It supports configuration of the backend service and retrieval behavior.

    Attributes:
        backend (Union[Literal["local", "opensearch", "redis", "viking", "viking_mem", "mem0", "openviking", "tos_context"], BaseLongTermMemoryBackend]):
            The type or instance of the long-term memory backend. Defaults to "opensearch".

        backend_config (dict):
            Configuration parameters for the selected backend. Defaults to an empty dictionary.

        top_k (int):
            The number of top similar documents to retrieve during search. Defaults to 5.

        index (str):
            The name of the index or collection used for storing memory items. Defaults to an empty string.

        app_name (str):
            The name of the application that owns this memory instance. Defaults to an empty string.

        user_id (str):
            Deprecated attribute. Retained for backward compatibility. Defaults to an empty string.

    Notes:
        Please ensure that you have set the embedding-related configurations in environment variables.
    """

    backend: Union[
        Literal[
            "local",
            "opensearch",
            "redis",
            "viking",
            "viking_mem",
            "mem0",
            "openviking",
            "tos_context",
        ],
        BaseLongTermMemoryBackend,
    ] = "opensearch"

    backend_config: dict = Field(default_factory=dict)

    top_k: int = 5

    index: str = ""

    app_name: str = ""

    user_id: str = ""

    def model_post_init(self, __context: Any) -> None:
        # Once user define a backend instance, use it directly
        if isinstance(self.backend, BaseLongTermMemoryBackend):
            self._backend = self.backend
            self.index = self._backend.index
            logger.info(
                f"Initialized long term memory with provided backend instance {self._backend.__class__.__name__}, index={self.index}"
            )
            return

        # Once user define backend config, use it directly
        if self.backend_config:
            if "index" not in self.backend_config:
                logger.warning(
                    "Attribute `index` not provided in backend_config, use `index` or `app_name` instead."
                )
                self.backend_config["index"] = self.index or self.app_name

            logger.debug(
                f"Init {self.backend}, Use provided backend config: {self.backend_config}"
            )
            self._backend = _get_backend_cls(self.backend)(**self.backend_config)
            return

        # Check index
        self.index = self.index or self.app_name
        if not self.index:
            logger.warning(
                "Attribute `index` or `app_name` not provided, use `default_app` instead."
            )
            self.index = "default_app"

        # Forward compliance
        if self.backend == "viking_mem":
            logger.warning(
                "The `viking_mem` backend is deprecated, change to `viking` instead."
            )
            self.backend = "viking"

        self._backend = _get_backend_cls(self.backend)(index=self.index)

        logger.info(
            f"Initialized long term memory with provided backend instance {self._backend.__class__.__name__}, index={self.index}"
        )

    def _filter_and_convert_events(
        self,
        events: Iterable[Event],
        *,
        include_assistant: bool = False,
        auto_save_memory_policy: MemoryAutoSavePolicyInput = None,
    ) -> list[str]:
        policy = self._resolve_auto_save_memory_policy(
            auto_save_memory_policy,
            include_assistant=include_assistant,
        )
        final_events = []
        for event in events:
            message = self._convert_event_to_memory_message(event, policy)
            if not message:
                continue

            final_events.append(json.dumps(message, ensure_ascii=False))
        return final_events

    def _resolve_auto_save_memory_policy(
        self,
        auto_save_memory_policy: MemoryAutoSavePolicyInput,
        *,
        include_assistant: bool,
    ) -> MemoryAutoSavePolicy:
        if auto_save_memory_policy is None:
            return self._base_auto_save_memory_policy(
                "default", include_assistant=include_assistant
            )

        if isinstance(auto_save_memory_policy, str):
            return self._base_auto_save_memory_policy(
                auto_save_memory_policy,
                include_assistant=include_assistant,
            )

        raw_policy = MemoryAutoSavePolicy.model_validate(auto_save_memory_policy)
        base_policy = self._base_auto_save_memory_policy(
            raw_policy.preset,
            include_assistant=include_assistant,
        )
        fields_set = getattr(raw_policy, "model_fields_set", set())
        overrides = {
            field: getattr(raw_policy, field)
            for field in fields_set
            if field != "preset"
        }
        if overrides:
            base_policy = base_policy.model_copy(update=overrides)
        return base_policy

    def _base_auto_save_memory_policy(
        self, preset: MemoryAutoSavePreset, *, include_assistant: bool
    ) -> MemoryAutoSavePolicy:
        if preset == "all":
            return MemoryAutoSavePolicy(
                preset="all",
                include_roles=["user", "assistant", "system"],
                include_event_types=None,
                text_only=False,
                include_thought=True,
                include_empty_text=True,
            )
        if preset == "custom":
            return MemoryAutoSavePolicy(preset="custom")
        return MemoryAutoSavePolicy(
            preset="default",
            include_roles=["user", "assistant"] if include_assistant else ["user"],
            include_event_types=["text"],
            text_only=True,
            include_thought=False,
            include_empty_text=False,
        )

    def _convert_event_to_memory_message(
        self, event: Event, policy: MemoryAutoSavePolicy
    ) -> dict[str, Any] | None:
        message = (
            event.content.model_dump(exclude_none=True, mode="json")
            if event.content
            else {"parts": []}
        )
        role = self._normalize_event_role(event, message)
        author = str(getattr(event, "author", "") or "")

        if not self._is_role_allowed(role, policy):
            return None
        if not self._is_author_allowed(author, policy):
            return None

        event_types = self._infer_event_types(event)
        if not self._has_allowed_event_type(event_types, policy):
            return None

        parts = self._filter_memory_parts(message.get("parts") or [], policy)
        parts.extend(self._event_metadata_parts(event, policy))
        if not parts and not policy.include_empty_text:
            return None

        message["role"] = role
        message["parts"] = parts
        if author and policy.preset != "default":
            message["author"] = author
        return message

    def _normalize_event_role(self, event: Event, message: dict[str, Any]) -> str:
        role = message.get("role")
        if event.author == "user" or role == "user":
            return "user"
        if role == "system":
            return "system"
        return "assistant"

    def _is_role_allowed(self, role: str, policy: MemoryAutoSavePolicy) -> bool:
        if policy.include_roles is not None and role not in policy.include_roles:
            return False
        return role not in policy.exclude_roles

    def _is_author_allowed(self, author: str, policy: MemoryAutoSavePolicy) -> bool:
        if policy.include_authors is not None and author not in policy.include_authors:
            return False
        return author not in policy.exclude_authors

    def _has_allowed_event_type(
        self, event_types: set[str], policy: MemoryAutoSavePolicy
    ) -> bool:
        if not event_types:
            return bool(policy.include_empty_text)
        event_types = event_types - set(policy.exclude_event_types)
        if not event_types:
            return False
        if policy.include_event_types is None:
            return True
        return bool(event_types & set(policy.include_event_types))

    def _filter_memory_parts(
        self, parts: list[Any], policy: MemoryAutoSavePolicy
    ) -> list[dict[str, Any]]:
        final_parts = []
        for part in parts:
            if not isinstance(part, dict):
                continue
            part_types = self._infer_part_event_types(part)
            if not self._has_allowed_part_type(part_types, policy):
                continue
            if "thought" in part_types and not policy.include_thought:
                part = dict(part)
                part.pop("thought", None)
                part.pop("thought_signature", None)
                if part_types == {"thought"}:
                    continue
            final_parts.append(self._sanitize_memory_part(part))
        return final_parts

    def _has_allowed_part_type(
        self, part_types: set[str], policy: MemoryAutoSavePolicy
    ) -> bool:
        if not part_types:
            return False
        if (
            policy.text_only
            and policy.include_event_types is None
            and not part_types <= {"text", "thought"}
        ):
            return False
        if part_types & set(policy.exclude_event_types):
            return False
        if policy.include_event_types is None:
            return True
        return bool(part_types & set(policy.include_event_types))

    def _infer_event_types(self, event: Event) -> set[str]:
        event_types = set()
        content = getattr(event, "content", None)
        for part in getattr(content, "parts", None) or []:
            if hasattr(part, "model_dump"):
                part = part.model_dump(exclude_none=True, mode="json")
            if isinstance(part, dict):
                event_types.update(self._infer_part_event_types(part))

        if getattr(event, "input_transcription", None) is not None:
            event_types.add("transcription")
        if getattr(event, "output_transcription", None) is not None:
            event_types.add("transcription")
        if getattr(event, "error_code", None) or getattr(event, "error_message", None):
            event_types.add("error")
        return event_types

    def _infer_part_event_types(self, part: dict[str, Any]) -> set[str]:
        part_types = set()
        text = part.get("text")
        if text:
            part_types.add("thought" if part.get("thought") else "text")
        if part.get("function_call") is not None:
            part_types.add("function_call")
        if part.get("function_response") is not None:
            part_types.add("function_response")
        if part.get("tool_call") is not None:
            part_types.add("tool_call")
        if part.get("tool_response") is not None:
            part_types.add("tool_response")
        if part.get("inline_data") is not None or part.get("file_data") is not None:
            part_types.add("media")
        if part.get("executable_code") is not None:
            part_types.add("executable_code")
        if part.get("code_execution_result") is not None:
            part_types.add("code_execution_result")
        return part_types

    def _event_metadata_parts(
        self, event: Event, policy: MemoryAutoSavePolicy
    ) -> list[dict[str, Any]]:
        metadata_parts = []
        if self._is_event_type_allowed("transcription", policy):
            metadata_parts.extend(
                self._serialize_event_metadata(
                    "input_transcription",
                    getattr(event, "input_transcription", None),
                )
            )
            metadata_parts.extend(
                self._serialize_event_metadata(
                    "output_transcription",
                    getattr(event, "output_transcription", None),
                )
            )
        if self._is_event_type_allowed("error", policy):
            error_code = getattr(event, "error_code", None)
            error_message = getattr(event, "error_message", None)
            if error_code or error_message:
                text = ": ".join(str(v) for v in (error_code, error_message) if v)
                metadata_parts.append(
                    {
                        "text": text,
                        "part_metadata": {"event_type": "error"},
                    }
                )
        return metadata_parts

    def _is_event_type_allowed(
        self, event_type: MemoryEventType, policy: MemoryAutoSavePolicy
    ) -> bool:
        if (
            policy.text_only
            and policy.include_event_types is None
            and event_type not in {"text", "thought"}
        ):
            return False
        if event_type in policy.exclude_event_types:
            return False
        if event_type == "thought" and not policy.include_thought:
            return False
        if policy.include_event_types is None:
            return True
        return event_type in policy.include_event_types

    def _serialize_event_metadata(self, name: str, value: Any) -> list[dict[str, Any]]:
        if value is None:
            return []
        if hasattr(value, "model_dump"):
            value = value.model_dump(exclude_none=True, mode="json")
        if isinstance(value, str):
            text = value
        else:
            text = json.dumps(value, ensure_ascii=False)
        if not text:
            return []
        return [{"text": text, "part_metadata": {"event_type": name}}]

    def _sanitize_memory_part(self, part: dict[str, Any]) -> dict[str, Any]:
        sanitized = dict(part)
        inline_data = sanitized.get("inline_data")
        if isinstance(inline_data, dict) and "data" in inline_data:
            sanitized["inline_data"] = self._sanitize_inline_data(inline_data)
        return sanitized

    def _sanitize_inline_data(self, inline_data: dict[str, Any]) -> dict[str, Any]:
        sanitized = dict(inline_data)
        data = sanitized.pop("data", None)
        if data is not None:
            sanitized["data_size"] = len(str(data))
            sanitized["data_omitted"] = True
        return sanitized

    @override
    async def add_session_to_memory(
        self,
        session: Session,
        **kwargs,
    ):
        """Add a chat session's events to the long-term memory backend.

        This method extracts and filters the events from a given `Session` object,
        converts them into serialized strings, and stores them into the long-term
        memory system. It is typically called after a chat session ends or when
        important contextual data needs to be persisted for future retrieval.

        Args:
            session (Session):
                The session object containing user ID and a list of events to persist.

        Examples:
            ```python
            session = Session(
                user_id="user_123",
                events=[
                    Event(role="user", content="I like Go and Rust."),
                    Event(role="assistant", content="Got it! I'll remember that."),
                ]
            )

            await memory_service.add_session_to_memory(session)
            # Logs:
            # Adding 2 events to long term memory: index=main
            # Added 2 events to long term memory: index=main, user_id=user_123
            ```
        """
        user_id = session.user_id
        save_kwargs = dict(kwargs)
        nested_kwargs = save_kwargs.pop("kwargs", None)
        if isinstance(nested_kwargs, dict):
            save_kwargs.update(nested_kwargs)
        auto_save_memory_policy = save_kwargs.pop("auto_save_memory_policy", None)
        app_name = self.app_name or getattr(session, "app_name", "")
        include_assistant = (
            self.backend == "openviking"
            or self._backend.__class__.__name__ == "OpenVikingLTMBackend"
        )
        event_strings = self._filter_and_convert_events(
            session.events,
            include_assistant=include_assistant,
            auto_save_memory_policy=auto_save_memory_policy,
        )

        logger.info(
            f"Adding {len(event_strings)} events to long term memory: index={self.index}"
        )
        save_call = {
            "user_id": user_id,
            "event_strings": event_strings,
            "session_id": session.id,
            "app_name": app_name,
            **save_kwargs,
        }
        if self._uses_openviking_backend():
            await asyncio.to_thread(self._backend.save_memory, **save_call)
        else:
            self._backend.save_memory(**save_call)
        logger.info(
            f"Added {len(event_strings)} events to long term memory: index={self.index}, user_id={user_id}"
        )

    @override
    async def search_memory(
        self, *, app_name: str, user_id: str, query: str
    ) -> SearchMemoryResponse:
        """Search memory entries for a given user and query.

        This method queries the memory backend to retrieve the most relevant stored
        memory chunks for a given user and text query. It then converts those raw
        memory chunks into structured `MemoryEntry` objects to be returned to the caller.

        Args:
            app_name (str): Name of the application requesting the memory search.
            user_id (str): Unique identifier for the user whose memory is being queried.
            query (str): The text query to match against stored memory content.

        Returns:
            SearchMemoryResponse:
                An object containing a list of `MemoryEntry` items representing
                the retrieved memory snippets relevant to the query.
        """
        logger.info(f"Search memory with query={query}")

        memory_chunks = []
        try:
            search_kwargs = {"app_name": app_name}
            search_call = {
                "query": query,
                "top_k": self.top_k,
                "user_id": user_id,
                **search_kwargs,
            }
            if self._uses_openviking_backend():
                memory_chunks = await asyncio.to_thread(
                    self._backend.search_memory,
                    **search_call,
                )
            else:
                memory_chunks = self._backend.search_memory(**search_call)
        except Exception as e:
            logger.error(
                f"Exception orrcus during memory search: {e}. Return empty memory chunks"
            )

        memory_events = []
        for memory in memory_chunks:
            memory_events.extend(self._convert_memory_chunk_to_entries(memory))

        logger.info(
            f"Return {len(memory_events)} memory events for query: {query} index={self.index} user_id={user_id}"
        )
        return SearchMemoryResponse(memories=memory_events)

    def _uses_openviking_backend(self) -> bool:
        return (
            self.backend == "openviking"
            or self._backend.__class__.__name__ == "OpenVikingLTMBackend"
        )

    def _convert_memory_chunk_to_entries(self, memory: str) -> list[MemoryEntry]:
        try:
            memory_dict = json.loads(memory)
        except json.JSONDecodeError:
            return [
                MemoryEntry(
                    author="user",
                    content=types.Content(
                        parts=[types.Part(text=memory)],
                        role="user",
                    ),
                )
            ]

        if not isinstance(memory_dict, dict):
            return [
                MemoryEntry(
                    author="user",
                    content=types.Content(
                        parts=[types.Part(text=str(memory_dict))],
                        role="user",
                    ),
                )
            ]

        memories = memory_dict.get("memories")
        if isinstance(memories, list):
            entries = []
            for item in memories:
                if isinstance(item, dict):
                    entry = self._convert_memory_dict_to_entry(item)
                    if entry:
                        entries.append(entry)
                else:
                    entries.extend(self._convert_memory_chunk_to_entries(str(item)))
            return entries

        entry = self._convert_memory_dict_to_entry(memory_dict)
        return [entry] if entry else []

    def _convert_memory_dict_to_entry(
        self, memory_dict: dict[str, Any]
    ) -> MemoryEntry | None:
        content = memory_dict.get("content")
        if isinstance(content, dict):
            role = str(content.get("role") or memory_dict.get("role") or "user")
            text = self._extract_memory_parts_text(content.get("parts") or [])
        else:
            role = str(memory_dict.get("role") or "user")
            text = self._extract_memory_parts_text(memory_dict.get("parts") or [])
            if not text:
                text = self._extract_memory_text_field(memory_dict)

        if not text:
            logger.warning(f"Memory content: {memory_dict}. Skip return this memory.")
            return None

        custom_metadata = memory_dict.get("custom_metadata")
        if not isinstance(custom_metadata, dict):
            custom_metadata = self._extract_memory_custom_metadata(memory_dict)

        return MemoryEntry(
            author=memory_dict.get("author", "user"),
            content=types.Content(parts=[types.Part(text=text)], role=role),
            custom_metadata=custom_metadata,
            id=memory_dict.get("id") or memory_dict.get("uri"),
            timestamp=memory_dict.get("timestamp"),
        )

    def _extract_memory_custom_metadata(
        self, memory_dict: dict[str, Any]
    ) -> dict[str, Any]:
        metadata_keys = (
            "context_type",
            "uri",
            "level",
            "score",
            "category",
            "match_reason",
            "relations",
            "overview",
        )
        return {key: memory_dict[key] for key in metadata_keys if key in memory_dict}

    def _extract_memory_parts_text(self, parts: list[Any]) -> str:
        text_parts = []
        for part in parts:
            text = self._extract_memory_part_text(part)
            if text:
                text_parts.append(text)
        return "\n".join(text_parts)

    def _extract_memory_part_text(self, part: Any) -> str:
        if isinstance(part, dict):
            if "text" in part:
                return self._clean_memory_text(part["text"])
            return json.dumps(part, ensure_ascii=False)
        if isinstance(part, str):
            try:
                parsed = ast.literal_eval(part)
            except (ValueError, SyntaxError):
                return self._clean_memory_text(part)
            if isinstance(parsed, dict) and "text" in parsed:
                return self._clean_memory_text(parsed["text"])
            if isinstance(parsed, str):
                return self._clean_memory_text(parsed)
            return json.dumps(parsed, ensure_ascii=False)
        return str(part)

    def _extract_memory_text_field(self, memory_dict: dict[str, Any]) -> str:
        for key in ("text", "abstract", "summary", "content"):
            value = memory_dict.get(key)
            if value and not isinstance(value, dict):
                return self._clean_memory_text(value)
        return ""

    def _clean_memory_text(self, value: Any) -> str:
        text = str(value)
        for _ in range(2):
            stripped = text.strip()
            if not (
                len(stripped) >= 2
                and stripped[0] == stripped[-1]
                and stripped[0] in {"'", '"'}
            ):
                return stripped
            try:
                parsed = ast.literal_eval(stripped)
            except (ValueError, SyntaxError):
                return stripped[1:-1]
            if not isinstance(parsed, str):
                return str(parsed)
            text = parsed
        return text.strip()

    def get_user_profile(self, user_id: str) -> str:
        logger.info(f"Get user profile for user_id={user_id}")
        if self.backend == "viking":
            return self._backend.get_user_profile(user_id=user_id)  # type: ignore
        else:
            logger.error(
                f"Long term memory backend {self.backend} does not support get user profile. Return empty string."
            )
            return ""
