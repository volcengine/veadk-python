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

"""Contract tests for the ``web_fetch`` built-in tool.

``web_fetch`` is exposed to agents as a function tool, so its signature *is* the
schema the model sees. These tests pin the parameter names and defaults and the
shape of the dict it returns, without making any network request.
"""

import inspect

from veadk.tools import get_builtin_tool
from veadk.tools.builtin_tools.web_fetch import web_fetch


def test_signature():
    sig = inspect.signature(web_fetch)
    assert list(sig.parameters) == ["url", "extract_mode", "max_chars", "tool_context"]


def test_defaults():
    params = inspect.signature(web_fetch).parameters
    assert params["url"].default is inspect.Parameter.empty  # required
    assert params["extract_mode"].default == "markdown"
    assert isinstance(params["max_chars"].default, int)
    assert params["tool_context"].default is None


def test_registered_as_web_fetch():
    assert get_builtin_tool("web_fetch") is web_fetch


def test_invalid_url_returns_error_dict():
    # A non-public / malformed URL must fail closed with an "error" key rather
    # than raising — the agent gets a tool result, not an exception.
    result = web_fetch("not-a-valid-url")
    assert isinstance(result, dict)
    assert "error" in result
