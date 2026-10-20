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

import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import Mock, patch

import httpx
import pytest

from veadk.cloud.cloud_agent_engine import CloudAgentEngine
from veadk.cloud.cloud_app import CloudApp


@pytest.fixture(autouse=True)
def clean_network_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY"):
        monkeypatch.delenv(key, raising=False)
        monkeypatch.delenv(key.lower(), raising=False)
    for key in ("SSL_CERT_FILE", "SSL_CERT_DIR"):
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def http_server() -> Iterator[tuple[str, list[tuple[str, str]]]]:
    requests: list[tuple[str, str]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            requests.append((self.command, self.path))
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"ok")

        def do_CONNECT(self) -> None:
            requests.append((self.command, self.path))
            # Record the selected HTTPS proxy without contacting the destination
            self.send_error(502, "Test proxy")

        def log_message(self, *_args: object) -> None:
            pass

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        thread = threading.Thread(
            target=lambda: server.serve_forever(poll_interval=0.01), daemon=True
        )
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}", requests
        finally:
            server.shutdown()
            thread.join(timeout=2)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "unused_proxy", ["ALL_PROXY", "all_proxy", "HTTPS_PROXY", "https_proxy"]
)
async def test_cloud_app_connects_directly_with_unrelated_invalid_proxy(
    monkeypatch: pytest.MonkeyPatch,
    http_server: tuple[str, list[tuple[str, str]]],
    unused_proxy: str,
) -> None:
    endpoint, requests = http_server
    monkeypatch.setenv("HTTP_PROXY", "")
    monkeypatch.setenv("http_proxy", "")
    monkeypatch.setenv(unused_proxy, "socks://127.0.0.1:7897")

    app = CloudApp(vefaas_endpoint=endpoint)
    async with app.httpx_client as client:
        response = await client.get(f"{endpoint}/health", timeout=2)

    assert response.text == "ok"
    assert requests == [("GET", "/health")]


@pytest.mark.asyncio
@pytest.mark.parametrize("scheme", ["http", "https"])
@pytest.mark.parametrize("proxy_case", ["uppercase", "lowercase", "empty_uppercase"])
async def test_cloud_app_routes_through_sdk_selected_proxy(
    monkeypatch: pytest.MonkeyPatch,
    http_server: tuple[str, list[tuple[str, str]]],
    scheme: str,
    proxy_case: str,
) -> None:
    proxy, requests = http_server
    upper_key = f"{scheme.upper()}_PROXY"
    lower_key = f"{scheme}_proxy"
    invalid_proxy = "socks://127.0.0.1:7897"
    monkeypatch.setenv("ALL_PROXY", invalid_proxy)
    monkeypatch.setenv("all_proxy", invalid_proxy)
    # The VeFaaS SDK does not apply NO_PROXY to its selected proxy
    monkeypatch.setenv("NO_PROXY", "studio.example")
    monkeypatch.setenv(
        "HTTPS_PROXY" if scheme == "http" else "HTTP_PROXY", invalid_proxy
    )
    if proxy_case == "uppercase":
        monkeypatch.setenv(upper_key, proxy)
        monkeypatch.setenv(lower_key, invalid_proxy)
    else:
        monkeypatch.setenv(lower_key, proxy)
        if proxy_case == "empty_uppercase":
            monkeypatch.setenv(upper_key, "")

    endpoint = f"{scheme}://studio.example/health"
    app = CloudApp(vefaas_endpoint=endpoint)
    async with app.httpx_client as client:
        if scheme == "http":
            response = await client.get(endpoint, timeout=2)
            assert response.text == "ok"
        else:
            with pytest.raises(httpx.ProxyError, match="502 Test proxy"):
                await client.get(endpoint, timeout=2)

    assert requests == (
        [("GET", endpoint)] if scheme == "http" else [("CONNECT", "studio.example:443")]
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["volcengine", "byteplus"])
async def test_cloud_deploy_returns_app_with_invalid_all_proxy(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, provider: str
) -> None:
    monkeypatch.setenv("ALL_PROXY", "socks://127.0.0.1:7897")
    endpoint = f"https://studio.{provider}.example"
    service = Mock()
    service.deploy.return_value = (endpoint, "application-id", "function-id")
    service.get_application_route.return_value = ("gateway", "service", "route")
    with (
        patch("veadk.cloud.cloud_agent_engine.VeFaaS", return_value=service),
        patch("veadk.cloud.cloud_agent_engine.APIGateway"),
        patch("veadk.cloud.cloud_agent_engine.IdentityClient"),
    ):
        engine = CloudAgentEngine(
            volcengine_access_key="test_access_key",
            volcengine_secret_key="test_secret_key",
            provider=provider,
        )
        app = engine.deploy("studio-app", str(tmp_path))

    try:
        assert app.vefaas_endpoint == endpoint
        assert app.vefaas_application_id == "application-id"
        service.deploy.assert_called_once()
    finally:
        await app.httpx_client.aclose()


@pytest.mark.parametrize("scheme", ["http", "https"])
def test_cloud_app_rejects_invalid_selected_proxy(
    monkeypatch: pytest.MonkeyPatch, scheme: str
) -> None:
    monkeypatch.setenv(f"{scheme.upper()}_PROXY", "socks://127.0.0.1:7897")

    with pytest.raises(ValueError, match="Unknown scheme for proxy URL"):
        CloudApp(vefaas_endpoint=f"{scheme}://studio.example")


def test_cloud_app_preserves_custom_certificate_configuration(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    certificate_file = tmp_path / "missing-ca.pem"
    monkeypatch.setenv("SSL_CERT_FILE", str(certificate_file))

    # A missing CA file must still fail, rather than silently using a default CA
    with pytest.raises(FileNotFoundError):
        CloudApp(vefaas_endpoint="https://studio.example")
