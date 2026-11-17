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

"""CUA integration tests run when the independent MCP wheel is installed.

Install tests/tools/cua_mcp/requirements.txt to execute this suite. Without the
wheel these tests are reported as skipped; no sibling repository or private MCP
source checkout is loaded into sys.path.
"""

import importlib.util

import pytest

_CUA_MCP_INSTALLED = importlib.util.find_spec("agentkit_cua_mcp") is not None


def pytest_collection_modifyitems(config, items):
    if _CUA_MCP_INSTALLED:
        return
    skip = pytest.mark.skip(
        reason="install tests/tools/cua_mcp/requirements.txt to run CUA integration tests"
    )
    for item in items:
        item.add_marker(skip)
