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

"""ADK tools whose execution is dispatched to the connected Studio BFF."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Protocol

from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.base_toolset import BaseToolset
from google.adk.tools.tool_context import ToolContext
from google.genai import types

from veadk.integrations.agentkit.studio_channel.protocol import StudioToolManifest


class StudioToolDispatcher(Protocol):
    async def call_tool(
        self,
        *,
        run_id: str,
        scope_id: str,
        catalog_revision: str,
        manifest: StudioToolManifest,
        arguments: dict[str, Any],
    ) -> Any: ...


_current_studio_tools: ContextVar[tuple[BaseTool, ...]] = ContextVar(
    "veadk_current_studio_tools",
    default=(),
)


class StudioExternalToolset(BaseToolset):
    """Resolve the current run's BFF tools without mutating the shared Agent."""

    _veadk_internal_toolset = True

    def __init__(self) -> None:
        super().__init__()
        # BaseToolset's invocation cache is shared by this singleton. The
        # ContextVar is already an immutable per-run snapshot, so resolving it
        # on every model request is both cheaper to reason about and safe under
        # concurrent invocations.
        self._use_invocation_cache = False

    async def get_tools(
        self,
        readonly_context: ReadonlyContext | None = None,
    ) -> list[BaseTool]:
        del readonly_context
        return list(_current_studio_tools.get())


@contextmanager
def bind_studio_tools(tools: Sequence[BaseTool]) -> Iterator[None]:
    """Bind an immutable Studio tool snapshot to the current async run."""

    token = _current_studio_tools.set(tuple(tools))
    try:
        yield
    finally:
        _current_studio_tools.reset(token)


class StudioRemoteTool(BaseTool):
    """A concrete model-visible tool backed by one BFF WebSocket connection."""

    def __init__(
        self,
        *,
        manifest: StudioToolManifest,
        dispatcher: StudioToolDispatcher,
        run_id: str,
        scope_id: str,
        catalog_revision: str,
    ) -> None:
        super().__init__(
            name=manifest.name,
            description=manifest.description,
            custom_metadata={
                "studio_catalog_revision": catalog_revision,
                "studio_executor_revision": manifest.executor_revision,
            },
        )
        self._manifest = manifest
        self._dispatcher = dispatcher
        self._run_id = run_id
        self._scope_id = scope_id
        self._catalog_revision = catalog_revision

    def _get_declaration(self) -> types.FunctionDeclaration:
        return types.FunctionDeclaration(
            name=self.name,
            description=self.description,
            parameters_json_schema=self._manifest.input_schema,
        )

    async def run_async(
        self,
        *,
        args: dict[str, Any],
        tool_context: ToolContext,
    ) -> Any:
        del tool_context
        return await self._dispatcher.call_tool(
            run_id=self._run_id,
            scope_id=self._scope_id,
            catalog_revision=self._catalog_revision,
            manifest=self._manifest,
            arguments=args,
        )
