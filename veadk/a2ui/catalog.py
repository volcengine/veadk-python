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

"""A2UI catalog helpers and the enterprise extension point.

A2UI (https://a2ui.org) lets an agent reply with declarative UI instead of plain
text. The set of components an agent may use is described by a *catalog* (a JSON
Schema document). The catalog is both the instruction the model reads and the
validator that rejects anything off-catalog.

This module provides:

* :func:`get_basic_catalog` -- the bundled Google "basic" catalog, ready to use.
* :class:`BaseA2UICatalog` -- the class an enterprise subclasses to register its
  own components (the *backend half* of a custom component; the *frontend half*
  is a ``frontend/src/a2ui/components/<Name>/`` directory that renders it).

All ``a2ui`` imports are deferred so that importing this module never requires the
optional ``a2ui-agent-sdk`` dependency unless a catalog is actually built.
"""

from __future__ import annotations

import abc
from typing import TYPE_CHECKING, Optional, Tuple

from veadk.utils.logger import get_logger

if TYPE_CHECKING:
    from a2ui.schema.catalog import A2uiCatalog

logger = get_logger(__name__)

# Default A2UI catalog version. The bundled basic catalog ships 0.8 and 0.9; 0.9
# is the first to expose ``createSurface`` / ``updateComponents`` cleanly.
DEFAULT_A2UI_VERSION = "0.9"

# A built catalog is always paired with its few-shot examples string (may be "").
BuiltCatalog = Tuple["A2uiCatalog", str]

_IMPORT_ERROR_HINT = (
    "A2UI support requires the optional `a2ui-agent-sdk` dependency. "
    "Install it with: pip install veadk-python[a2ui]"
)


def _import_a2ui():
    """Import the a2ui SDK pieces, raising a friendly error if it is missing."""
    try:
        from a2ui.basic_catalog.provider import BasicCatalog
        from a2ui.schema.manager import A2uiSchemaManager
    except ImportError as e:  # pragma: no cover - exercised only without the extra
        raise ImportError(_IMPORT_ERROR_HINT) from e
    return A2uiSchemaManager, BasicCatalog


def get_basic_catalog(
    version: str = DEFAULT_A2UI_VERSION,
    examples_path: Optional[str] = None,
) -> BuiltCatalog:
    """Build the bundled Google "basic" A2UI catalog.

    Args:
        version: A2UI catalog version (``"0.8"`` or ``"0.9"``).
        examples_path: Optional path/glob to few-shot example JSON files that are
            injected into the system prompt alongside the schema.

    Returns:
        A ``(A2uiCatalog, examples_str)`` tuple ready for
        :func:`veadk.a2ui.toolset.build_a2ui_toolset`.
    """
    A2uiSchemaManager, BasicCatalog = _import_a2ui()
    manager = A2uiSchemaManager(
        version=version,
        catalogs=[
            BasicCatalog.get_config(version=version, examples_path=examples_path)
        ],
    )
    catalog = manager.get_selected_catalog()
    examples = manager.load_examples(catalog)
    logger.debug(
        f"Built basic A2UI catalog '{catalog.catalog_id}' (examples: {len(examples)} chars)"
    )
    return catalog, examples


class BaseA2UICatalog(abc.ABC):
    """Base class enterprises subclass to expose their own A2UI components.

    The simplest integration is to point ``catalog_path`` (and optionally
    ``examples_path``) at your own catalog JSON / examples directory::

        class FinanceCatalog(BaseA2UICatalog):
            version = "0.9"
            catalog_path = "/opt/corp/a2ui/finance_catalog.json"
            examples_path = "/opt/corp/a2ui/finance_examples"

        agent = Agent(enable_a2ui=True, a2ui_catalog=FinanceCatalog())

    For full control, override :meth:`build` and return a ready
    ``(A2uiCatalog, examples_str)`` tuple yourself.

    Each component declared in the catalog must have a matching frontend renderer
    under ``frontend/src/a2ui/components/<ComponentName>/``.
    """

    #: A2UI catalog version.
    version: str = DEFAULT_A2UI_VERSION
    #: Local filesystem path (or ``file://`` URI) to the catalog JSON.
    catalog_path: Optional[str] = None
    #: Optional path/glob to few-shot example JSON files.
    examples_path: Optional[str] = None

    def build(self) -> BuiltCatalog:
        """Return the ``(A2uiCatalog, examples_str)`` pair for this catalog.

        The default implementation loads ``catalog_path`` via the a2ui SDK. When
        ``catalog_path`` is unset it falls back to the bundled basic catalog.
        """
        if not self.catalog_path:
            logger.warning(
                f"{type(self).__name__}.catalog_path is unset; falling back to the "
                "bundled basic A2UI catalog."
            )
            return get_basic_catalog(self.version, self.examples_path)

        try:
            from a2ui.schema.catalog import CatalogConfig
            from a2ui.schema.manager import A2uiSchemaManager
        except ImportError as e:  # pragma: no cover
            raise ImportError(_IMPORT_ERROR_HINT) from e

        config = CatalogConfig.from_path(
            name=type(self).__name__,
            catalog_path=self.catalog_path,
            examples_path=self.examples_path,
        )
        manager = A2uiSchemaManager(version=self.version, catalogs=[config])
        catalog = manager.get_selected_catalog()
        examples = manager.load_examples(catalog)
        return catalog, examples
