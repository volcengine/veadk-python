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

from typing import TYPE_CHECKING, Optional, Union

from veadk.a2ui.catalog import BaseA2UICatalog, BuiltCatalog, get_basic_catalog
from veadk.utils.logger import get_logger

if TYPE_CHECKING:
    from a2ui.adk.send_a2ui_to_client_toolset import SendA2uiToClientToolset
    from a2ui.schema.catalog import A2uiCatalog

logger = get_logger(__name__)

# Anything accepted as the ``a2ui_catalog`` argument of :class:`veadk.Agent`.
A2UICatalogLike = Union[BaseA2UICatalog, "A2uiCatalog", BuiltCatalog, None]


def _resolve_catalog(catalog: A2UICatalogLike) -> BuiltCatalog:
    """Normalise the various accepted catalog forms into ``(A2uiCatalog, str)``."""
    if catalog is None:
        return get_basic_catalog()
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
) -> "SendA2uiToClientToolset":
    """Build a ``SendA2uiToClientToolset`` for the given catalog.

    Args:
        catalog: A :class:`BaseA2UICatalog`, an ``A2uiCatalog``, a pre-built
            ``(A2uiCatalog, examples)`` tuple, or ``None`` for the bundled basic
            catalog.
        examples: Optional override for the few-shot examples string.
        enabled: Whether the toolset is active (passed through as ``a2ui_enabled``).

    Returns:
        A configured ``SendA2uiToClientToolset`` (an ADK ``BaseToolset``).
    """
    try:
        from a2ui.adk.send_a2ui_to_client_toolset import SendA2uiToClientToolset
    except ImportError as e:  # pragma: no cover - exercised only without the extra
        raise ImportError(
            "A2UI support requires the optional `a2ui-agent-sdk` dependency. "
            "Install it with: pip install veadk-python[a2ui]"
        ) from e

    a2ui_catalog, default_examples = _resolve_catalog(catalog)
    return SendA2uiToClientToolset(
        a2ui_enabled=enabled,
        a2ui_catalog=a2ui_catalog,
        a2ui_examples=examples if examples is not None else default_examples,
    )
