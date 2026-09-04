from agentkit.sdk.tools.client import AgentkitToolsClient

from frontend.server.agentkit_clients import create_agentkit_client


def test_tools_client_preserves_vestack_endpoint_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("VOLCENGINE_AGENTKIT_HOST", "agentkit.e70.inspirecloud.io")
    monkeypatch.setenv("VOLCENGINE_AGENTKIT_SCHEME", "http")

    client = create_agentkit_client(
        AgentkitToolsClient,
        provider="volcengine",
        access_key="temporary-ak",
        secret_key="temporary-sk",
        session_token="temporary-token",
        region="e70",
    )

    assert client.host == "agentkit.e70.inspirecloud.io"
    assert client.scheme == "http"
    assert client.region == "e70"
