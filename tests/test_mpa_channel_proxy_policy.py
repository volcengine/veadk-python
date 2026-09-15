import pytest
from fastapi import HTTPException

from veadk.integrations.mpa.channel_proxy import channel_management_headers


def test_channel_policy_requires_admin_and_never_proxies_ingress():
    for path in ("api/v1/channels", "api/v1/channels/feishu/bindings"):
        with pytest.raises(HTTPException) as error:
            channel_management_headers(path, is_admin=False, api_key="example")
        assert error.value.status_code == 403
    with pytest.raises(HTTPException):
        channel_management_headers(
            "api/v1/channels/events", is_admin=True, api_key="example"
        )
    assert channel_management_headers(
        "api/v1/channels", is_admin=True, api_key="Bearer example"
    ) == {"X-MPA-Channel-Key": "example"}
    assert channel_management_headers("apps", is_admin=False, api_key="example") == {}
    with pytest.raises(HTTPException):
        channel_management_headers("api/v1/channels", is_admin=True, api_key="")


@pytest.mark.parametrize(
    "path",
    [
        "api/v1/channels/../sessions",
        "api/v1/%63hannels/events",
        "api//v1/channels",
        "api/v1/channels%2Fevents",
    ],
)
def test_noncanonical_paths_are_rejected(path):
    with pytest.raises(HTTPException):
        channel_management_headers(path, is_admin=True, api_key="example")


def test_proxy_header_builder_strips_browser_channel_credentials():
    from veadk.cli.cli_frontend import _build_agentkit_proxy_headers

    headers = _build_agentkit_proxy_headers(
        {"X-MPA-Channel-Key": "untrusted", "x-mpa-channel-key": "untrusted"},
        "server-key",
    )
    assert not any(name.lower() == "x-mpa-channel-key" for name in headers)
    assert headers["Authorization"] == "Bearer server-key"
