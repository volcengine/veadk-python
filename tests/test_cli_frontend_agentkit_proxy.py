from veadk.cli.cli_frontend import (
    _agentkit_authorization_header,
    _build_agentkit_proxy_headers,
)


def test_agentkit_proxy_headers_drop_local_auth_and_use_agentkit_key():
    headers = _build_agentkit_proxy_headers(
        {
            "host": "localhost:8000",
            "authorization": "Bearer local-sso-token",
            "cookie": "veadk_session=local-session",
            "x-agentkit-base": "https://agentkit.example.com",
            "x-agentkit-key": "agentkit-api-key",
            "content-type": "application/json",
        },
        "agentkit-api-key",
    )

    assert headers == {
        "content-type": "application/json",
        "Authorization": "Bearer agentkit-api-key",
    }


def test_agentkit_proxy_headers_normalize_existing_bearer_prefix():
    assert (
        _agentkit_authorization_header("Bearer agentkit-api-key")
        == "Bearer agentkit-api-key"
    )
