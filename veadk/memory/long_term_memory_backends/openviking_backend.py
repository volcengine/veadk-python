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

from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections.abc import Callable
from typing import Any

from openviking_sdk import SyncHTTPClient
from pydantic import Field
from typing_extensions import override

import veadk.config  # noqa: F401  # Load .env and config.yaml before settings.
from veadk.configs.database_configs import OpenVikingConfig
from veadk.memory.long_term_memory_backends.base_backend import (
    BaseLongTermMemoryBackend,
)
from veadk.utils.logger import get_logger

logger = get_logger(__name__)

_SAFE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.@-]+$")
_UNSAFE_ID_CHARS = re.compile(r"[^A-Za-z0-9_.@-]+")


def default_peer_id_resolver(app_name: str, user_id: str) -> str:
    del app_name
    return user_id


class OpenVikingLTMBackend(BaseLongTermMemoryBackend):
    """OpenViking long term memory backend using the OpenViking SDK."""

    openviking_config: OpenVikingConfig = Field(default_factory=OpenVikingConfig)
    url: str = ""
    api_key: str = ""
    openviking_user_id: str = ""
    memory_policy: dict[str, Any] | None = None
    peer_id_resolver: Callable[[str, str], str] | None = None
    timeout: float = 30

    def model_post_init(self, __context: Any, /) -> None:
        self.url = (self.url or self.openviking_config.url).rstrip("/")
        self.api_key = self.api_key or self.openviking_config.api_key
        configured_openviking_user_id = (
            self.openviking_user_id or self.openviking_config.user_id
        ).strip()
        using_default_openviking_user_id = not configured_openviking_user_id
        self.openviking_user_id = self._validate_safe_path_segment(
            configured_openviking_user_id or "default",
            name="openviking_user_id",
        )
        if not self.url:
            raise ValueError(
                "OpenViking URL is required. Set DATABASE_OPENVIKING_URL or pass url."
            )
        if not self.api_key:
            raise ValueError(
                "OpenViking API key is required. Set DATABASE_OPENVIKING_API_KEY or pass api_key."
            )
        if using_default_openviking_user_id:
            logger.warning(
                "OpenViking long-term memory `openviking_user_id` is not configured. "
                "VeADK `user_id` identifies the current requester and is used as "
                "OpenViking `peer_id`. OpenViking `openviking_user_id` identifies "
                "the memory owner/context in `viking://user/<openviking_user_id>/...`. "
                "Falling back to OpenViking user_id='default'. Set "
                "backend_config['openviking_user_id'] or DATABASE_OPENVIKING_USER_ID "
                "to isolate memories by agent/context."
            )
        self.memory_policy = (
            self.memory_policy
            if self.memory_policy is not None
            else self.openviking_config.memory_policy
        )
        if not self.peer_id_resolver:
            self.peer_id_resolver = default_peer_id_resolver

    def precheck_index_naming(self):
        if not self.index:
            raise ValueError("OpenViking backend index/app_name must not be empty")

    @override
    def save_memory(
        self,
        user_id: str,
        event_strings: list[str],
        **kwargs,
    ) -> bool:
        if not event_strings:
            return True

        app_name = kwargs.get("app_name") or self.index
        session_id = kwargs.get("session_id") or str(uuid.uuid4())
        peer_id = self._resolve_peer_id(app_name=app_name, user_id=user_id)
        openviking_session_id = self._openviking_session_id(
            app_name=app_name,
            openviking_user_id=self.openviking_user_id,
            peer_id=peer_id,
            session_id=session_id,
        )

        client = self._new_client()
        try:
            client.initialize()
            self._create_session(client=client, session_id=openviking_session_id)
            for event_string in event_strings:
                role, content = self._parse_event_string(event_string)
                self._add_message(
                    client=client,
                    session_id=openviking_session_id,
                    role=role,
                    content=content,
                    peer_id=peer_id,
                )
            self._commit_session(client=client, session_id=openviking_session_id)
        finally:
            client.close()
        return True

    @override
    def search_memory(
        self,
        user_id: str,
        query: str,
        top_k: int,
        **kwargs,
    ) -> list[str]:
        app_name = kwargs.get("app_name") or self.index
        peer_id = self._resolve_peer_id(app_name=app_name, user_id=user_id)

        response = self._search_with_actor_client(
            peer_id=peer_id,
            query=query,
            top_k=top_k,
        )
        return self._extract_memories(response)

    def _resolve_peer_id(self, *, app_name: str, user_id: str) -> str:
        assert self.peer_id_resolver is not None
        peer_id = str(self.peer_id_resolver(app_name, user_id) or "").strip()
        return self._validate_safe_path_segment(peer_id, name="peer_id")

    def _validate_safe_path_segment(self, value: str, *, name: str) -> str:
        value = str(value or "").strip()
        if not value:
            raise ValueError(f"OpenViking {name} must not be empty")
        if value in {".", ".."} or not _SAFE_ID_PATTERN.match(value):
            raise ValueError(
                f"OpenViking {name} must be a safe single path segment. "
                "Allowed characters: letters, digits, '.', '_', '@', '-'."
            )
        return value

    def _peer_memory_target_uri(self, *, peer_id: str) -> str:
        return f"viking://user/{self.openviking_user_id}/peers/{peer_id}/memories"

    def _openviking_session_id(
        self,
        *,
        app_name: str,
        openviking_user_id: str,
        peer_id: str,
        session_id: str,
    ) -> str:
        return "__".join(
            [
                "veadk",
                self._safe_identifier_part(app_name, fallback="app"),
                self._safe_identifier_part(openviking_user_id, fallback="user"),
                self._safe_identifier_part(peer_id, fallback="peer"),
                self._safe_identifier_part(session_id, fallback="session"),
            ]
        )

    def _safe_identifier_part(self, value: Any, *, fallback: str) -> str:
        raw = str(value or "").strip()
        normalized = _UNSAFE_ID_CHARS.sub("_", raw).strip("._-")
        if not normalized or normalized in {".", ".."}:
            normalized = fallback
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
        return f"{normalized[:48]}_{digest}"

    def _new_client(self, *, actor_peer_id: str | None = None) -> SyncHTTPClient:
        return SyncHTTPClient(
            url=self.url,
            api_key=self.api_key,
            actor_peer_id=actor_peer_id,
            timeout=self.timeout,
        )

    def _create_session(self, *, client: SyncHTTPClient, session_id: str) -> None:
        try:
            kwargs: dict[str, Any] = {"session_id": session_id}
            if self.memory_policy is not None:
                kwargs["memory_policy"] = self.memory_policy
            client.create_session(**kwargs)
        except Exception as e:
            if self._is_existing_session_error(e):
                logger.debug(f"OpenViking session already exists, continue: {e}")
                return
            raise

    def _add_message(
        self,
        *,
        client: SyncHTTPClient,
        session_id: str,
        role: str,
        content: str,
        peer_id: str,
    ) -> None:
        client.add_message(
            session_id=session_id,
            role=role,
            content=content,
            peer_id=peer_id,
        )

    def _commit_session(self, *, client: SyncHTTPClient, session_id: str) -> None:
        client.commit_session(session_id=session_id, keep_recent_count=0)

    def _search_with_actor_client(
        self, *, peer_id: str, query: str, top_k: int
    ) -> dict[str, Any]:
        target_uri = self._peer_memory_target_uri(peer_id=peer_id)
        client = self._new_client(actor_peer_id=peer_id)
        try:
            client.initialize()
            return client.find(
                query=query,
                target_uri=target_uri,
                context_type="memory",
                limit=top_k,
            )
        finally:
            client.close()

    def _is_existing_session_error(self, error: Exception) -> bool:
        code = str(getattr(error, "code", "")).replace("_", "").upper()
        message = str(error).lower()
        return (
            code in {"ALREADYEXISTS", "ALREADYEXISTSERROR", "CONFLICT"}
            or "already" in message
        )

    def _parse_event_string(self, event_string: str) -> tuple[str, str]:
        try:
            event = json.loads(event_string)
        except json.JSONDecodeError:
            return "user", event_string

        role = self._normalize_role(event.get("role"))
        content = self._extract_text_from_event(event)
        if not content:
            content = event_string
        return role, content

    def _normalize_role(self, role: Any) -> str:
        if role == "user":
            return "user"
        if role == "system":
            return "system"
        return "assistant"

    def _extract_text_from_event(self, event: dict[str, Any]) -> str:
        parts = event.get("parts") or []
        text_parts = []
        for part in parts:
            if not isinstance(part, dict):
                continue
            text = part.get("text")
            if text:
                text_parts.append(str(text))
        return "\n".join(text_parts)

    def _extract_memories(self, response: dict[str, Any]) -> list[str]:
        result = response.get("result")
        result = result if isinstance(result, dict) else response
        memories = result.get("memories") or response.get("memories") or []
        return [
            memory
            for memory in (
                self._memory_to_text(item)
                for item in self._deduplicate_memory_items(memories)
            )
            if memory
        ]

    def _deduplicate_memory_items(self, memories: list[Any]) -> list[Any]:
        deduplicated: list[Any] = []
        key_to_index: dict[str, int] = {}
        for item in memories:
            key = self._memory_dedupe_key(item)
            if not key:
                deduplicated.append(item)
                continue

            existing_index = key_to_index.get(key)
            if existing_index is None:
                key_to_index[key] = len(deduplicated)
                deduplicated.append(item)
                continue

            existing = deduplicated[existing_index]
            if self._memory_score(item) > self._memory_score(existing):
                deduplicated[existing_index] = item
        return deduplicated

    def _memory_dedupe_key(self, item: Any) -> str:
        if isinstance(item, dict):
            uri = str(item.get("uri") or "").strip()
            if uri:
                return f"uri:{uri}"
            return f"dict:{json.dumps(item, ensure_ascii=False, sort_keys=True)}"
        if isinstance(item, str):
            return f"str:{item}"
        return ""

    def _memory_score(self, item: Any) -> float:
        if not isinstance(item, dict):
            return 0
        try:
            return float(item.get("score") or 0)
        except (TypeError, ValueError):
            return 0

    def _memory_to_text(self, item: Any) -> str:
        if isinstance(item, str):
            return item
        if not isinstance(item, dict):
            return str(item)
        return json.dumps(item, ensure_ascii=False)
