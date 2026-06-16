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

"""Factory for the A2UI ADK toolset used by :class:`veadk.Agent`.

When an agent has ``enable_a2ui=True``, this builds Google's
``SendA2uiToClientToolset`` and attaches it to the agent's tools. The toolset:

* injects the catalog schema + few-shot examples into the system instructions, and
* exposes a ``send_a2ui_json_to_client`` tool the model calls to emit validated
  A2UI JSON (which then flows to a client over the ADK API server ``/run_sse``
  stream as a function response).
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, Optional, Union

from google.adk.tools import base_tool, base_toolset

from veadk.a2ui.catalog import (
    DEFAULT_CATALOG_FILENAME,
    DEFAULT_EXAMPLES_DIRNAME,
    BaseA2UICatalog,
    BuiltCatalog,
    get_basic_catalog,
    load_catalog,
)
from veadk.utils.logger import get_logger

if TYPE_CHECKING:
    from a2ui.adk.send_a2ui_to_client_toolset import SendA2uiToClientToolset
    from a2ui.schema.catalog import A2uiCatalog

logger = get_logger(__name__)

# Anything accepted as the ``a2ui_catalog`` argument of :class:`veadk.Agent`.
#   - str               -> path to a catalog JSON (relative = resolved against
#                          the agent's directory; absolute used as-is)
#   - BaseA2UICatalog   -> custom subclass
#   - A2uiCatalog       -> a pre-built catalog
#   - (A2uiCatalog, str)-> a pre-built (catalog, examples) pair
#   - None              -> auto-discover `catalog.json` next to the agent, else
#                          the bundled basic catalog
A2UICatalogLike = Union[str, BaseA2UICatalog, "A2uiCatalog", BuiltCatalog, None]


def _load_send_a2ui_toolset_class():
    """Import the SDK toolset, with a fallback for known SDK annotation issues."""
    try:
        from a2ui.adk.send_a2ui_to_client_toolset import SendA2uiToClientToolset

        return SendA2uiToClientToolset
    except ImportError as e:  # pragma: no cover - exercised only without the extra
        raise ImportError(
            "A2UI support requires the optional `a2ui-agent-sdk` dependency. "
            "Install it with: pip install veadk-python[a2ui]"
        ) from e
    except NameError as e:
        if "models" not in str(e):
            raise
        logger.warning(
            "The installed a2ui-agent-sdk failed to import due to a known "
            "`models.LlmRequest` annotation issue; using VeADK's compatible "
            "A2UI toolset fallback."
        )
        return _FallbackSendA2uiToClientToolset


class _FallbackSendA2uiToClientToolset(base_toolset.BaseToolset):
    """Small compatibility copy of the SDK's ADK toolset.

    Some a2ui-agent-sdk releases import `LlmRequest` but annotate with
    `models.LlmRequest`, which raises `NameError` at import time. This fallback
    keeps the public behavior VeADK needs: inject catalog instructions and expose
    `send_a2ui_json_to_client` returning `validated_a2ui_json`.
    """

    def __init__(
        self,
        a2ui_enabled: bool,
        a2ui_catalog: "A2uiCatalog",
        a2ui_examples: str,
    ):
        super().__init__()
        self._a2ui_enabled = a2ui_enabled
        self._ui_tools = [self._SendA2uiJsonToClientTool(a2ui_catalog, a2ui_examples)]

    async def get_tools(self, readonly_context=None):
        if self._a2ui_enabled:
            return self._ui_tools
        return []

    async def close(self) -> None:
        return None

    class _SendA2uiJsonToClientTool(base_tool.BaseTool):
        TOOL_NAME = "send_a2ui_json_to_client"
        VALIDATED_A2UI_JSON_KEY = "validated_a2ui_json"
        A2UI_JSON_ARG_NAME = "a2ui_json"
        TOOL_ERROR_KEY = "a2ui_tool_error"

        def __init__(self, a2ui_catalog: "A2uiCatalog", a2ui_examples: str):
            super().__init__(
                name=self.TOOL_NAME,
                description=(
                    "Sends A2UI JSON to the client to render rich UI for the user. "
                    f"Args: {self.A2UI_JSON_ARG_NAME}: valid A2UI JSON to send."
                ),
            )
            self._a2ui_catalog = a2ui_catalog
            self._a2ui_examples = a2ui_examples

        def _get_declaration(self):
            from google.genai import types as genai_types

            return genai_types.FunctionDeclaration(
                name=self.name,
                description=self.description,
                parameters=genai_types.Schema(
                    type=genai_types.Type.OBJECT,
                    properties={
                        self.A2UI_JSON_ARG_NAME: genai_types.Schema(
                            type=genai_types.Type.STRING,
                            description="valid A2UI JSON to send to the client.",
                        ),
                    },
                    required=[self.A2UI_JSON_ARG_NAME],
                ),
            )

        async def process_llm_request(
            self,
            *,
            tool_context: Any,
            llm_request: Any,
        ) -> None:
            await super().process_llm_request(
                tool_context=tool_context, llm_request=llm_request
            )
            instruction = self._a2ui_catalog.render_as_llm_instructions()
            llm_request.append_instructions([instruction, self._a2ui_examples])
            logger.info("Added A2UI schema and examples to system instructions")

        async def run_async(self, *, args: dict[str, Any], tool_context: Any) -> Any:
            from a2ui.parser.payload_fixer import parse_and_fix

            try:
                a2ui_json = args.get(self.A2UI_JSON_ARG_NAME)
                if not a2ui_json:
                    raise ValueError(f"Missing required arg {self.A2UI_JSON_ARG_NAME}")

                a2ui_json_payload = parse_and_fix(a2ui_json)
                self._a2ui_catalog.validator.validate(a2ui_json_payload)
                tool_context.actions.skip_summarization = True
                return {self.VALIDATED_A2UI_JSON_KEY: a2ui_json_payload}
            except Exception as e:
                err = f"Failed to call A2UI tool {self.TOOL_NAME}: {e}"
                logger.error(err)
                return {self.TOOL_ERROR_KEY: err}


def _examples_beside(catalog_path: str) -> Optional[str]:
    """Return the conventional examples dir next to a catalog file, if present."""
    ex = os.path.join(os.path.dirname(catalog_path), DEFAULT_EXAMPLES_DIRNAME)
    return ex if os.path.isdir(ex) else None


def caller_agent_dir() -> Optional[str]:
    """Best-effort directory of the user module that constructed the agent.

    Walks the call stack and returns the directory of the first frame outside the
    ``veadk`` package and site-packages (i.e. the user's ``agent.py``). Used to
    resolve relative catalog paths and to auto-discover ``catalog.json``.
    """
    import inspect

    veadk_root = os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))
    )  # .../veadk
    for frame in inspect.stack():
        fn = frame.filename
        if not fn or fn.startswith("<"):
            continue
        absfn = os.path.abspath(fn)
        if absfn.startswith(veadk_root + os.sep):
            continue
        if "site-packages" in absfn or f"{os.sep}pydantic{os.sep}" in absfn:
            continue
        return os.path.dirname(absfn)
    return None


def _resolve_catalog(catalog: A2UICatalogLike, base_dir: Optional[str]) -> BuiltCatalog:
    """Normalise the accepted catalog forms into ``(A2uiCatalog, str)``.

    ``base_dir`` is the agent's directory: relative string paths resolve against
    it, and it is searched for a ``catalog.json`` when ``catalog`` is ``None``.
    """
    if catalog is None:
        if base_dir:
            candidate = os.path.join(base_dir, DEFAULT_CATALOG_FILENAME)
            if os.path.isfile(candidate):
                logger.info(f"Using A2UI catalog beside the agent: {candidate}")
                return load_catalog(
                    candidate, examples_path=_examples_beside(candidate)
                )
        return get_basic_catalog()

    if isinstance(catalog, str):
        path = (
            catalog
            if os.path.isabs(catalog)
            else os.path.join(base_dir or os.getcwd(), catalog)
        )
        return load_catalog(path, examples_path=_examples_beside(path))

    if isinstance(catalog, BaseA2UICatalog):
        return catalog.build()
    if isinstance(catalog, tuple) and len(catalog) == 2:
        return catalog  # already a (A2uiCatalog, examples) pair
    # A bare A2uiCatalog instance: pair it with empty examples.
    return catalog, ""


def build_a2ui_toolset(
    catalog: A2UICatalogLike = None,
    examples: Optional[str] = None,
    enabled: bool = True,
    base_dir: Optional[str] = None,
) -> "SendA2uiToClientToolset":
    """Build a ``SendA2uiToClientToolset`` for the given catalog.

    Args:
        catalog: See :data:`A2UICatalogLike` for accepted forms.
        examples: Optional override for the few-shot examples string.
        enabled: Whether the toolset is active (passed through as ``a2ui_enabled``).
        base_dir: The agent's directory, used to resolve relative catalog paths
            and to auto-discover ``catalog.json``.

    Returns:
        A configured ``SendA2uiToClientToolset`` (an ADK ``BaseToolset``).
    """
    SendA2uiToClientToolset = _load_send_a2ui_toolset_class()

    if base_dir is None:
        base_dir = caller_agent_dir()
    a2ui_catalog, default_examples = _resolve_catalog(catalog, base_dir)
    return SendA2uiToClientToolset(
        a2ui_enabled=enabled,
        a2ui_catalog=a2ui_catalog,
        a2ui_examples=examples if examples is not None else default_examples,
    )
