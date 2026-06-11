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

"""Contract tests for the built-in tool registry (``veadk.tools``).

The Harness server resolves harness ``tools`` strings through this registry, so
a renamed/removed built-in tool would break harnesses that reference it by name.
These tests pin the registry API and the set of advertised names.
"""

import inspect
import os

import pytest

# Some generation tools (image/video) read ``settings.model.api_key`` at import
# time, which fetches a live ARK token over the network when MODEL_AGENT_API_KEY
# is unset (e.g. in CI). Provide a dummy so resolving every tool stays offline;
# a real value in the local environment is preserved by setdefault.
os.environ.setdefault("MODEL_AGENT_API_KEY", "test-model-api-key")

from veadk.tools import get_builtin_tool, list_builtin_tools  # noqa: E402

# Names that callers (harnesses, docs, examples) rely on. New tools may be
# added freely; removing/renaming one should be a deliberate, reviewed change
# that updates this list.
_EXPECTED_NAMES = {
    "web_search",
    "web_fetch",
    "parallel_web_search",
    "vesearch",
    "link_reader",
    "run_code",
    "coding",
    "image_generate",
    "image_edit",
    "video_generate",
    "text_to_speech",
}


def test_list_builtin_tools_is_sorted():
    names = list_builtin_tools()
    assert names == sorted(names)


def test_expected_names_present():
    assert _EXPECTED_NAMES <= set(list_builtin_tools())


def test_get_builtin_tool_signature():
    sig = inspect.signature(get_builtin_tool)
    assert list(sig.parameters) == ["name"]


@pytest.mark.parametrize("name", sorted(_EXPECTED_NAMES))
def test_every_advertised_tool_resolves(name):
    # Lazy import inside get_builtin_tool must succeed and return something
    # callable/usable (a function or a tool/toolset object).
    tool = get_builtin_tool(name)
    assert tool is not None


def test_unknown_tool_raises_key_error():
    with pytest.raises(KeyError):
        get_builtin_tool("definitely_not_a_tool")
