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

import os
import tempfile
from pathlib import Path
from typing import Any

from pydantic import Field, PrivateAttr
from typing_extensions import override

from veadk.knowledgebase.backends.base_backend import BaseKnowledgebaseBackend
from veadk.knowledgebase.entry import KnowledgebaseEntry
from veadk.utils.logger import get_logger

logger = get_logger(__name__)


def _getenv(*names: str) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return None


def _parse_bool(value: str | None, default: bool) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "t", "yes", "y", "on"}


def _parse_int(value: str | None, default: int) -> int:
    if value is None or value == "":
        return default
    return int(value)


def _parse_float(value: str | None, default: float | None) -> float | None:
    if value is None or value == "":
        return default
    return float(value)


def _default_target_uri(index: str) -> str:
    return f"viking://resources/{index.strip('/')}/"


class OpenVikingKnowledgeBackend(BaseKnowledgebaseBackend):
    """OpenViking SDK backend for VeADK knowledge base operations.

    Each VeADK knowledgebase index maps to an OpenViking resources directory,
    e.g. ``viking://resources/{index}/``. Imported resources are written under
    that directory and searches are scoped with ``target_uri``. OpenViking
    performs resource parsing and indexing, so this backend does not require
    local embedding configuration.
    """

    url: str | None = Field(
        default_factory=lambda: _getenv("DATABASE_OPENVIKING_URL", "OPENVIKING_URL")
    )
    api_key: str | None = Field(
        default_factory=lambda: _getenv(
            "DATABASE_OPENVIKING_API_KEY", "OPENVIKING_API_KEY"
        )
    )
    account: str | None = Field(
        default_factory=lambda: _getenv(
            "DATABASE_OPENVIKING_ACCOUNT", "OPENVIKING_ACCOUNT"
        )
    )
    user: str | None = Field(
        default_factory=lambda: _getenv("DATABASE_OPENVIKING_USER", "OPENVIKING_USER")
    )
    actor_peer_id: str | None = Field(
        default_factory=lambda: _getenv(
            "DATABASE_OPENVIKING_ACTOR_PEER_ID", "OPENVIKING_ACTOR_PEER_ID"
        )
    )
    target_uri: str | None = Field(
        default_factory=lambda: _getenv(
            "DATABASE_OPENVIKING_TARGET_URI", "OPENVIKING_TARGET_URI"
        )
    )
    wait: bool = Field(
        default_factory=lambda: _parse_bool(
            os.getenv("DATABASE_OPENVIKING_WAIT"), default=True
        )
    )
    import_timeout: float | None = Field(
        default_factory=lambda: _parse_float(
            os.getenv("DATABASE_OPENVIKING_IMPORT_TIMEOUT"), default=300
        )
    )
    hydrate_results: bool = Field(
        default_factory=lambda: _parse_bool(
            os.getenv("DATABASE_OPENVIKING_HYDRATE_RESULTS"), default=True
        )
    )
    read_limit: int = Field(
        default_factory=lambda: _parse_int(
            os.getenv("DATABASE_OPENVIKING_READ_LIMIT"), default=200
        )
    )
    score_threshold: float | None = Field(
        default_factory=lambda: _parse_float(
            os.getenv("DATABASE_OPENVIKING_SCORE_THRESHOLD"), default=None
        )
    )
    use_context_search: bool = Field(
        default_factory=lambda: _parse_bool(
            os.getenv("DATABASE_OPENVIKING_USE_CONTEXT_SEARCH"), default=False
        )
    )

    _client: Any = PrivateAttr(default=None)

    def model_post_init(self, __context: Any) -> None:
        self.precheck_index_naming()
        self.target_uri = self._normalize_target_uri(
            self.target_uri or _default_target_uri(self.index)
        )
        self._client = self._build_client()

    @override
    def precheck_index_naming(self) -> None:
        if not isinstance(self.index, str) or not self.index.strip():
            raise ValueError(
                "OpenViking knowledgebase index must be a non-empty string."
            )

    def _build_client(self) -> Any:
        try:
            from openviking_sdk import SyncHTTPClient
        except ImportError as first_error:
            try:
                from openviking.client import SyncHTTPClient
            except ImportError as second_error:
                raise ImportError(
                    "OpenViking knowledgebase backend requires 'openviking-sdk'. "
                    "Please install it via `pip install openviking-sdk>=0.1.3`."
                ) from second_error
            logger.debug(f"Fallback import used after error: {first_error}")

        return SyncHTTPClient(
            url=self.url,
            api_key=self.api_key,
            account=self.account,
            user=self.user,
            actor_peer_id=self.actor_peer_id,
        )

    def _normalize_target_uri(self, target_uri: str) -> str:
        if not target_uri:
            return _default_target_uri(self.index)
        if target_uri.startswith("viking://resources/") and not target_uri.endswith(
            "/"
        ):
            return f"{target_uri}/"
        return target_uri

    @override
    def add_from_directory(self, directory: str, **kwargs) -> bool:
        self._client.add_resource(
            path=directory,
            to=kwargs.get("target_uri", self.target_uri),
            wait=kwargs.get("wait", self.wait),
            timeout=kwargs.get("timeout", self.import_timeout),
            strict=kwargs.get("strict", False),
            ignore_dirs=kwargs.get("ignore_dirs"),
            include=kwargs.get("include"),
            exclude=kwargs.get("exclude"),
            directly_upload_media=kwargs.get("directly_upload_media", True),
            preserve_structure=kwargs.get("preserve_structure", True),
            watch_interval=kwargs.get("watch_interval", 0),
            args=kwargs.get("args"),
            telemetry=kwargs.get("telemetry", False),
        )
        return True

    @override
    def add_from_files(self, files: list[str], **kwargs) -> bool:
        for file in files:
            self._client.add_resource(
                path=file,
                parent=kwargs.get("target_uri", self.target_uri),
                wait=kwargs.get("wait", self.wait),
                timeout=kwargs.get("timeout", self.import_timeout),
                strict=kwargs.get("strict", False),
                reason=kwargs.get("reason", ""),
                instruction=kwargs.get("instruction", ""),
                directly_upload_media=kwargs.get("directly_upload_media", True),
                telemetry=kwargs.get("telemetry", False),
            )
        return True

    @override
    def add_from_text(self, text: str | list[str], **kwargs) -> bool:
        texts = [text] if isinstance(text, str) else text
        with tempfile.TemporaryDirectory() as tmpdir:
            files = []
            for index, item in enumerate(texts):
                path = Path(tmpdir) / f"text_{index}.txt"
                path.write_text(item, encoding="utf-8")
                files.append(str(path))
            return self.add_from_files(files, **kwargs)

    @override
    def search(self, query: str, top_k: int = 5, **kwargs) -> list[KnowledgebaseEntry]:
        target_uri = kwargs.get("target_uri", self.target_uri)
        score_threshold = kwargs.get("score_threshold", self.score_threshold)
        use_context_search = kwargs.get("use_context_search", self.use_context_search)
        method = self._client.search if use_context_search else self._client.find

        call_kwargs = {
            "query": query,
            "target_uri": target_uri,
            "limit": top_k,
            "score_threshold": score_threshold,
            "filter": kwargs.get("filter"),
            "context_type": kwargs.get("context_type"),
            "tags": kwargs.get("tags"),
            "telemetry": kwargs.get("telemetry", False),
        }
        if use_context_search:
            call_kwargs["session"] = kwargs.get("session")
            call_kwargs["session_id"] = kwargs.get("session_id")

        result = method(**call_kwargs)
        return self._to_entries(result)

    def _to_entries(self, response: Any) -> list[KnowledgebaseEntry]:
        result = self._unwrap_result(response)
        resources = self._extract_resources(result)
        entries: list[KnowledgebaseEntry] = []

        for item in resources:
            if not isinstance(item, dict):
                continue
            uri = str(item.get("uri") or "")
            abstract = item.get("abstract") or ""
            content = self._hydrate(uri, item) if self.hydrate_results else abstract
            metadata = {
                "uri": uri,
                "score": item.get("score"),
                "match_reason": item.get("match_reason"),
                "context_type": item.get("context_type"),
                "is_leaf": item.get("is_leaf"),
            }
            entries.append(
                KnowledgebaseEntry(
                    content=str(content or abstract or ""),
                    metadata=metadata,
                )
            )

        return entries

    def _unwrap_result(self, response: Any) -> Any:
        if isinstance(response, dict) and isinstance(response.get("result"), dict):
            return response["result"]
        return response

    def _extract_resources(self, result: Any) -> list[Any]:
        if isinstance(result, dict):
            resources = result.get("resources", [])
            return resources if isinstance(resources, list) else []
        if isinstance(result, list):
            return result
        return []

    def _hydrate(self, uri: str, item: dict[str, Any]) -> str:
        if not uri:
            return str(item.get("abstract") or "")

        try:
            if item.get("is_leaf"):
                return self._client.read(uri, offset=0, limit=self.read_limit)
            return self._client.overview(uri)
        except Exception as e:
            logger.debug(f"Failed to hydrate OpenViking resource {uri}: {e}")
            return str(item.get("abstract") or "")
