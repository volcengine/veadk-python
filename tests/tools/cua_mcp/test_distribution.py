"""Distribution changes must not alter the CUA request/session contract."""

import asyncio

import pytest

from mcp import StdioServerParameters

from veadk.tools.builtin_tools import computer_use


def capture_params(monkeypatch):
    captured = []

    class Manager:
        def __init__(self, params):
            captured.append(params.server_params)

        async def close(self):
            pass

    monkeypatch.setattr(computer_use, "MCPSessionManager", Manager)
    return captured


def test_missing_wheel_url_fails_with_configuration_guidance(monkeypatch):
    capture_params(monkeypatch)
    monkeypatch.delenv("CUA_MCP_WHEEL_URL", raising=False)
    with pytest.raises(ValueError, match="CUA_MCP_WHEEL_URL"):
        computer_use.create_computer_use_toolset(tool_id="t-example")


def test_empty_wheel_url_fails_with_configuration_guidance(monkeypatch):
    capture_params(monkeypatch)
    monkeypatch.setenv("CUA_MCP_WHEEL_URL", "  ")
    with pytest.raises(ValueError, match="CUA_MCP_WHEEL_URL"):
        computer_use.create_computer_use_toolset(tool_id="t-example")


def test_explicit_wheel_and_uv_cache_configuration(monkeypatch):
    captured = capture_params(monkeypatch)
    wheel = "https://downloads.example.test/agentkit_cua_mcp-1.0.0-py3-none-any.whl"
    monkeypatch.setenv("CUA_MCP_WHEEL_URL", wheel)
    monkeypatch.setenv("UV_CACHE_DIR", "/opt/uv-cache")
    monkeypatch.setenv("UV_OFFLINE", "true")
    monkeypatch.setenv("UV_INDEX_URL", "https://pypi.org/simple")
    monkeypatch.setenv("UNRELATED_SECRET", "must-not-forward")
    cua = computer_use.create_computer_use_toolset(tool_id="t-example")
    params = captured[0]
    assert params.command == "uvx"
    assert params.args[1] == wheel
    assert params.env["UV_CACHE_DIR"] == "/opt/uv-cache"
    assert params.env["UV_OFFLINE"] == "true"
    assert params.env["UV_INDEX_URL"] == "https://pypi.org/simple"
    assert "UNRELATED_SECRET" not in params.env
    assert "CUA_MCP_WHEEL_URL" not in params.env
    asyncio.run(cua.close())


def test_explicit_connection_still_supports_preinstalled_server(monkeypatch):
    captured = capture_params(monkeypatch)
    monkeypatch.setenv("CUA_MCP_WHEEL_URL", "not-used")
    params = StdioServerParameters(
        command="agentkit-cua-mcp", args=["--transport", "stdio"], env={}
    )
    cua = computer_use.create_computer_use_toolset(
        tool_id="t-example", connection_params=params
    )
    assert captured[0].command == "agentkit-cua-mcp"
    assert captured[0].args == params.args
    assert params.env == {}  # Do not mutate caller configuration.
    asyncio.run(cua.close())
