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
