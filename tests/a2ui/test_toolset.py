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

"""Unit tests for :mod:`veadk.a2ui.toolset`.

Covers catalog-form normalisation (``_resolve_catalog``), the conventional
examples-dir discovery (``_examples_beside``), and the public
``build_a2ui_toolset`` factory. The toolset is built against the real
``a2ui-agent-sdk`` (present in the venv); tool enablement is verified through a
mocked ``ReadonlyContext`` so no agent runtime is required.
"""

from __future__ import annotations

import os
import shutil
from typing import Any
from unittest.mock import Mock

import pytest

from veadk.a2ui import toolset as toolset_mod
from veadk.a2ui.toolset import (
    _examples_beside,
    _resolve_catalog,
    build_a2ui_toolset,
    caller_agent_dir,
)

_SDK_BASIC_CATALOG = os.path.join(
    os.path.dirname(__import__("a2ui").__file__),
    "assets",
    "0.9",
    "basic_catalog.json",
)

# Some tests build against the real a2ui SDK (catalog asset + toolset
# construction). CI may install an a2ui version whose assets/internals differ;
# the bundled 0.9 catalog being absent is a reliable proxy for that, so skip the
# real-SDK tests there rather than asserting against a foreign SDK build.
_requires_sdk_assets = pytest.mark.skipif(
    not os.path.isfile(_SDK_BASIC_CATALOG),
    reason="installed a2ui SDK lacks the bundled 0.9 basic_catalog.json asset",
)


def test_examples_beside_returns_dir_when_present(tmp_path):
    """The conventional ``a2ui_examples/`` dir beside a catalog is discovered."""
    catalog = tmp_path / "catalog.json"
    catalog.write_text("{}")
    ex_dir = tmp_path / "a2ui_examples"
    ex_dir.mkdir()

    assert _examples_beside(str(catalog)) == str(ex_dir)


def test_examples_beside_returns_none_when_absent(tmp_path):
    """No examples dir -> ``None`` (so the SDK default examples are used)."""
    catalog = tmp_path / "catalog.json"
    catalog.write_text("{}")

    assert _examples_beside(str(catalog)) is None


def test_resolve_catalog_none_no_base_dir_uses_basic(monkeypatch):
    """``catalog=None`` with no base dir falls back to the basic catalog."""
    monkeypatch.setattr(toolset_mod, "get_basic_catalog", lambda: ("BASIC", "BASIC_EX"))

    assert _resolve_catalog(None, None) == ("BASIC", "BASIC_EX")


def test_resolve_catalog_none_discovers_catalog_beside_agent(tmp_path, monkeypatch):
    """``catalog=None`` with a base dir auto-discovers a sibling ``catalog.json``."""
    (tmp_path / "catalog.json").write_text("{}")
    captured = {}

    def fake_load(path, examples_path=None):
        captured["path"] = path
        captured["examples_path"] = examples_path
        return ("DISCOVERED", "EX")

    monkeypatch.setattr(toolset_mod, "load_catalog", fake_load)

    result = _resolve_catalog(None, str(tmp_path))

    assert result == ("DISCOVERED", "EX")
    assert captured["path"] == os.path.join(str(tmp_path), "catalog.json")


def test_resolve_catalog_none_base_dir_without_catalog_uses_basic(
    tmp_path, monkeypatch
):
    """A base dir lacking ``catalog.json`` still falls back to the basic catalog."""
    monkeypatch.setattr(toolset_mod, "get_basic_catalog", lambda: ("BASIC", ""))

    assert _resolve_catalog(None, str(tmp_path)) == ("BASIC", "")


def test_resolve_catalog_relative_string_resolved_against_base_dir(monkeypatch):
    """A relative string path is joined onto ``base_dir`` before loading."""
    captured = {}

    def fake_load(path, examples_path=None):
        captured["path"] = path
        return ("C", "E")

    monkeypatch.setattr(toolset_mod, "load_catalog", fake_load)

    _resolve_catalog("sub/catalog.json", "/agents/app")

    assert captured["path"] == os.path.join("/agents/app", "sub/catalog.json")


def test_resolve_catalog_absolute_string_used_as_is(monkeypatch):
    """An absolute string path is used verbatim, ignoring ``base_dir``."""
    captured = {}

    def fake_load(path, examples_path=None):
        captured["path"] = path
        return ("C", "E")

    monkeypatch.setattr(toolset_mod, "load_catalog", fake_load)

    _resolve_catalog("/abs/catalog.json", "/agents/app")

    assert captured["path"] == "/abs/catalog.json"


def test_resolve_catalog_base_catalog_instance_calls_build():
    """A ``BaseA2UICatalog`` instance is normalised via its ``build()``."""

    class _Cat(toolset_mod.BaseA2UICatalog):
        def build(self) -> Any:
            return ("BUILT", "BUILT_EX")

    assert _resolve_catalog(_Cat(), None) == ("BUILT", "BUILT_EX")


def test_resolve_catalog_prebuilt_pair_passthrough():
    """A pre-built ``(catalog, examples)`` tuple is returned unchanged."""
    from veadk.a2ui.catalog import get_basic_catalog

    cat, _ = get_basic_catalog()
    pair = (cat, "examples")
    assert _resolve_catalog(pair, None) is pair


def test_resolve_catalog_bare_catalog_paired_with_empty_examples():
    """A bare ``A2uiCatalog`` instance is paired with an empty examples string."""
    from veadk.a2ui.catalog import get_basic_catalog

    bare, _ = get_basic_catalog()  # a genuine A2uiCatalog instance
    result = _resolve_catalog(bare, None)
    assert result == (bare, "")


def test_caller_agent_dir_skips_veadk_frames():
    """The caller dir is this test file's directory, not a veadk internal one."""
    result = caller_agent_dir()
    # This test module lives outside the veadk package, so it is the first
    # non-veadk, non-site-packages frame and should be returned.
    assert result == os.path.dirname(os.path.abspath(__file__))


def test_build_a2ui_toolset_import_error_is_friendly(monkeypatch):
    """A missing SDK raises the install hint rather than a raw ImportError."""
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "a2ui.adk.send_a2ui_to_client_toolset":
            raise ImportError("blocked for test")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(ImportError) as exc:
        build_a2ui_toolset()
    assert "a2ui-agent-sdk" in str(exc.value)


@_requires_sdk_assets
def test_build_a2ui_toolset_returns_base_toolset():
    """The factory returns a real ADK ``BaseToolset`` instance."""
    from google.adk.tools.base_toolset import BaseToolset

    ts = build_a2ui_toolset(base_dir=None)
    assert isinstance(ts, BaseToolset)


@_requires_sdk_assets
@pytest.mark.asyncio
async def test_toolset_exposes_send_tool_when_enabled():
    """An enabled toolset exposes exactly the ``send_a2ui_json_to_client`` tool."""
    ts = build_a2ui_toolset(enabled=True, base_dir=None)

    tools = await ts.get_tools(Mock())

    assert [t.name for t in tools] == ["send_a2ui_json_to_client"]


@_requires_sdk_assets
@pytest.mark.asyncio
async def test_toolset_hides_tool_when_disabled():
    """A disabled toolset exposes no tools."""
    ts = build_a2ui_toolset(enabled=False, base_dir=None)

    tools = await ts.get_tools(Mock())

    assert tools == []


@_requires_sdk_assets
def test_build_a2ui_toolset_passes_examples_override(tmp_path, monkeypatch):
    """An explicit ``examples`` override wins over the resolved default."""
    dest = tmp_path / "catalog.json"
    shutil.copyfile(_SDK_BASIC_CATALOG, dest)

    captured = {}

    class _FakeToolset:
        def __init__(self, *, a2ui_enabled, a2ui_catalog, a2ui_examples):
            captured["enabled"] = a2ui_enabled
            captured["examples"] = a2ui_examples

    monkeypatch.setattr(
        "a2ui.adk.send_a2ui_to_client_toolset.SendA2uiToClientToolset",
        _FakeToolset,
    )

    build_a2ui_toolset(
        catalog=str(dest),
        examples="OVERRIDE",
        enabled=False,
        base_dir=str(tmp_path),
    )

    assert captured["examples"] == "OVERRIDE"
    assert captured["enabled"] is False
