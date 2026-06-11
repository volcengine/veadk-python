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

"""Unit tests for :mod:`veadk.a2ui.catalog`.

These exercise the catalog helpers against the real ``a2ui-agent-sdk`` (installed
in the project venv) for the happy paths, and use mocking to assert the
``ImportError`` friendly-message behaviour and the ``BaseA2UICatalog`` dispatch
logic. No network or model access is involved.
"""

from __future__ import annotations

import os
import shutil
from typing import Any

import pytest

from veadk.a2ui import catalog as catalog_mod
from veadk.a2ui.catalog import (
    DEFAULT_A2UI_VERSION,
    DEFAULT_CATALOG_FILENAME,
    DEFAULT_EXAMPLES_DIRNAME,
    BaseA2UICatalog,
    get_basic_catalog,
    load_catalog,
)

# The real basic catalog JSON shipped with the a2ui SDK; used to test
# ``load_catalog`` against a genuine on-disk catalog file.
_SDK_BASIC_CATALOG = os.path.join(
    os.path.dirname(__import__("a2ui").__file__),
    "assets",
    "0.9",
    "basic_catalog.json",
)

# These tests load the real on-disk catalog shipped with the a2ui SDK. CI may
# install an a2ui version that doesn't ship the 0.9 asset; skip there rather
# than fail on a foreign SDK layout.
_requires_sdk_assets = pytest.mark.skipif(
    not os.path.isfile(_SDK_BASIC_CATALOG),
    reason="installed a2ui SDK lacks the bundled 0.9 basic_catalog.json asset",
)


def test_module_constants():
    """Public constants keep their documented defaults."""
    assert DEFAULT_A2UI_VERSION == "0.9"
    assert DEFAULT_CATALOG_FILENAME == "catalog.json"
    assert DEFAULT_EXAMPLES_DIRNAME == "a2ui_examples"


def test_get_basic_catalog_returns_catalog_and_examples():
    """The bundled basic catalog builds into a ``(catalog, examples)`` pair."""
    result = get_basic_catalog()

    assert isinstance(result, tuple)
    assert len(result) == 2
    cat, examples = result
    # The basic catalog id encodes the requested version.
    assert "0_9" in cat.catalog_id
    assert isinstance(examples, str)


def test_get_basic_catalog_honours_version():
    """Selecting the 0.8 catalog yields a 0.8 catalog id."""
    cat, _ = get_basic_catalog(version="0.8")
    assert "0_8" in cat.catalog_id


@_requires_sdk_assets
def test_load_catalog_from_real_file():
    """``load_catalog`` loads a genuine catalog JSON off disk."""
    assert os.path.isfile(_SDK_BASIC_CATALOG), "SDK basic catalog JSON missing"

    cat, examples = load_catalog(_SDK_BASIC_CATALOG)

    assert cat.catalog_id  # non-empty id
    assert isinstance(examples, str)


def test_load_catalog_import_error_is_friendly(monkeypatch):
    """A missing SDK surfaces the install hint, not a raw ImportError."""
    # ``load_catalog`` imports CatalogConfig lazily inside the function body;
    # block that import so the friendly fallback message is raised.
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name.startswith("a2ui.schema"):
            raise ImportError("blocked for test")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(ImportError) as exc:
        load_catalog("/nonexistent/catalog.json")
    assert "a2ui-agent-sdk" in str(exc.value)


def test_base_catalog_class_defaults():
    """The base class exposes the documented class-level configuration knobs."""
    assert BaseA2UICatalog.version == DEFAULT_A2UI_VERSION
    assert BaseA2UICatalog.catalog_path is None
    assert BaseA2UICatalog.examples_path is None


def test_base_catalog_build_falls_back_to_basic_when_unset(monkeypatch):
    """With no ``catalog_path``, ``build()`` defers to the basic catalog."""
    calls = {}

    def fake_basic(version, examples_path):
        calls["args"] = (version, examples_path)
        return ("CATALOG", "EXAMPLES")

    monkeypatch.setattr(catalog_mod, "get_basic_catalog", fake_basic)

    class _Empty(BaseA2UICatalog):
        version = "0.8"

    result = _Empty().build()

    assert result == ("CATALOG", "EXAMPLES")
    assert calls["args"] == ("0.8", None)


def test_base_catalog_build_uses_load_catalog_when_path_set(monkeypatch):
    """With ``catalog_path`` set, ``build()`` routes through ``load_catalog``."""
    calls = {}

    def fake_load(catalog_path, version, examples_path):
        calls["args"] = (catalog_path, version, examples_path)
        return ("LOADED", "EX")

    monkeypatch.setattr(catalog_mod, "load_catalog", fake_load)

    class _Custom(BaseA2UICatalog):
        version = "0.9"
        catalog_path = "/opt/corp/finance.json"
        examples_path = "/opt/corp/examples"

    result = _Custom().build()

    assert result == ("LOADED", "EX")
    assert calls["args"] == ("/opt/corp/finance.json", "0.9", "/opt/corp/examples")


def test_base_catalog_subclass_build_override():
    """A subclass may fully override ``build`` to supply its own pair."""

    class _Override(BaseA2UICatalog):
        def build(self) -> Any:
            return ("MY_CATALOG", "MY_EXAMPLES")

    assert _Override().build() == ("MY_CATALOG", "MY_EXAMPLES")


@_requires_sdk_assets
def test_load_catalog_copied_file(tmp_path):
    """A catalog copied to a temp dir still loads (path independence)."""
    dest = tmp_path / "my_catalog.json"
    shutil.copyfile(_SDK_BASIC_CATALOG, dest)

    cat, _ = load_catalog(str(dest))

    assert cat.catalog_id
