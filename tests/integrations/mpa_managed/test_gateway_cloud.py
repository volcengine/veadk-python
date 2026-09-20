import asyncio
import json
from types import SimpleNamespace

from veadk.integrations.mpa.managed.gateway_cloud import GatewayCloud


def test_gateway_reads_universal_sdk_raw_response_when_decoded_result_is_empty(
    monkeypatch,
):
    import volcenginesdkcore
    from volcenginesdkcore import universal

    credentials = SimpleNamespace(
        access_key_id="fake", secret_access_key="fake", session_token="fake"
    )
    raw = {"Result": {"Gateway": {"Id": "g-one"}}}
    client = SimpleNamespace(
        last_response=SimpleNamespace(data=json.dumps(raw).encode())
    )
    monkeypatch.setattr(volcenginesdkcore, "ApiClient", lambda config: client)
    monkeypatch.setattr(
        universal,
        "UniversalApi",
        lambda value: SimpleNamespace(do_call=lambda *a, **kw: {}),
    )
    cloud = GatewayCloud(
        SimpleNamespace(region="cn-beijing", _credentials=lambda: credentials)
    )
    assert asyncio.run(cloud.get_gateway("g-one")) == {"Id": "g-one"}
