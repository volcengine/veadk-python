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

"""Contract tests for ``veadk.tunnel``.

The tunnel has three sides (cloud / agent / enterprise connector) that talk to
each other across processes and machines. A drift in the public types, their
fields, or the wire ``descriptor()`` shape would silently break that handshake.
These tests pin the public surface; they create no sockets and dial no network.
"""

import dataclasses
import inspect

import veadk.tunnel as tunnel
from veadk.tunnel import (
    LocalServer,
    ServerDescriptor,
    TunnelConnector,
    TunnelRegistry,
    TunnelToolset,
    get_registry,
    mount_tunnel,
    mount_tunnel_if_enabled,
)


def test_public_exports():
    assert set(tunnel.__all__) == {
        "LocalServer",
        "TunnelConnector",
        "ServerDescriptor",
        "TunnelRegistry",
        "get_registry",
        "mount_tunnel",
        "mount_tunnel_if_enabled",
        "TunnelToolset",
    }
    for name in tunnel.__all__:
        assert hasattr(tunnel, name)


class TestLocalServer:
    def test_is_dataclass_with_expected_fields(self):
        assert dataclasses.is_dataclass(LocalServer)
        names = {f.name for f in dataclasses.fields(LocalServer)}
        assert names == {
            "name",
            "address",
            "protocol",
            "tool_filter",
            "headers",
            "query",
        }

    def test_protocol_default_is_mcp(self):
        server = LocalServer(name="db", address="http://host:9000/mcp")
        assert server.protocol == "mcp"

    def test_descriptor_keeps_address_connector_side(self):
        # descriptor() is sent to the cloud; address/headers/query must NOT be
        # in it (they stay on the connector).
        server = LocalServer(name="db", address="http://host:9000/mcp")
        descriptor = server.descriptor()
        assert set(descriptor) == {"name", "protocol", "tool_filter"}
        assert "address" not in descriptor


class TestServerDescriptor:
    def test_fields_and_defaults(self):
        fields = dict(ServerDescriptor.model_fields)
        assert set(fields) == {
            "name",
            "protocol",
            "address",
            "tool_filter",
            "headers",
            "query",
        }
        assert fields["protocol"].default == "mcp"
        assert fields["address"].default == ""
        assert fields["tool_filter"].default is None


class TestTunnelConnector:
    def test_init_signature(self):
        sig = inspect.signature(TunnelConnector.__init__)
        params = list(sig.parameters)
        assert params == [
            "self",
            "cloud_url",
            "agent",
            "servers",
            "token",
            "extra_headers",
        ]
        assert sig.parameters["token"].default is None
        assert sig.parameters["extra_headers"].default is None

    def test_start_is_coroutine(self):
        assert inspect.iscoroutinefunction(TunnelConnector.start)

    def test_cloud_url_is_stripped(self):
        connector = TunnelConnector(
            cloud_url="https://example.com/",
            agent="ops",
            servers=[LocalServer(name="db", address="http://host:9000/mcp")],
        )
        assert connector.cloud_url == "https://example.com"
        assert connector.agent == "ops"


class TestTunnelRegistry:
    def test_public_methods(self):
        for name in (
            "add_connection",
            "remove_connection",
            "list_servers",
            "find_connection",
            "has_agent",
        ):
            assert callable(getattr(TunnelRegistry, name))

    def test_get_registry_is_singleton(self):
        assert get_registry() is get_registry()
        assert isinstance(get_registry(), TunnelRegistry)

    def test_unknown_agent_has_no_servers(self):
        registry = TunnelRegistry()
        assert registry.has_agent("nobody") is False
        assert registry.list_servers("nobody") == []


class TestMountAndToolset:
    def test_mount_tunnel_signature(self):
        sig = inspect.signature(mount_tunnel)
        # `app` is positional; the rest are keyword-only with safe defaults.
        assert list(sig.parameters) == [
            "app",
            "token",
            "allowed_agents",
            "auth",
            "registry",
        ]
        for name in ("token", "allowed_agents", "auth", "registry"):
            assert sig.parameters[name].default is None

    def test_mount_tunnel_if_enabled_signature(self):
        sig = inspect.signature(mount_tunnel_if_enabled)
        assert list(sig.parameters)[:2] == ["app", "agents"]

    def test_toolset_init_signature(self):
        sig = inspect.signature(TunnelToolset.__init__)
        assert list(sig.parameters) == ["self", "agent_name", "registry"]
        assert sig.parameters["registry"].default is None
