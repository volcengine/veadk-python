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

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from agentkit.toolkit.errors import ApiError

from veadk.integrations.mpa.managed.diagnostics import diagnostic_scope
from veadk.integrations.mpa.managed.runtime import RuntimeCloud


@pytest.mark.parametrize("provider", ["byteplus", "volcengine"])
@pytest.mark.parametrize("method", ["create_runtime", "update_runtime"])
def test_sdk_failure_records_code_without_changing_payload_or_exception(
    monkeypatch, provider, method
):
    cloud = RuntimeCloud(
        region="ap-southeast-1" if provider == "byteplus" else "cn-beijing",
        credential_file="",
        provider=provider,
    )
    error = ApiError("private provider response", error_code="InvalidParameter.Runtime")
    api = Mock(side_effect=error)
    client = SimpleNamespace(**{method: api})
    monkeypatch.setattr(cloud, "_client", lambda **kwargs: client)
    request = SimpleNamespace(
        ClientToken="private-idempotency-token",
        Envs=[{"Key": "MODEL_AGENT_API_KEY", "Value": "private-model-key"}],
    )
    events = []
    with diagnostic_scope(events.append), pytest.raises(ApiError) as caught:
        asyncio.run(cloud.call(method, request))
    assert caught.value is error
    api.assert_called_once_with(request)
    assert request.ClientToken == "private-idempotency-token"
    assert events == [
        {
            "operation": method,
            "category": "provider_error",
            "attempt": 1,
            "outcome": "failed",
            "errorCode": "InvalidParameter.Runtime",
            "exceptionType": "ApiError",
        }
    ]
    assert "private" not in str(events)


def test_wrapped_error_uses_safe_structured_metadata_and_stops_on_cycle(monkeypatch):
    cloud = RuntimeCloud(region="cn-beijing", credential_file="")

    class SDKError(Exception):
        error_code = "AccessDenied"
        request_id = "20261014094649ABCDEF0123456789ABCD"

    inner = SDKError("private cause")
    outer = ApiError("private wrapper")
    outer.__cause__ = inner
    inner.__cause__ = outer
    api = Mock(side_effect=outer)
    monkeypatch.setattr(
        cloud, "_client", lambda **kwargs: SimpleNamespace(create_runtime=api)
    )
    events = []
    with diagnostic_scope(events.append), pytest.raises(ApiError):
        asyncio.run(cloud.call("create_runtime", object()))
    assert events[-1]["errorCode"] == "AccessDenied"
    assert events[-1]["requestId"] == inner.request_id
    assert "private" not in str(events)


@pytest.mark.parametrize(
    "code", [None, "sk-private-token", "SK_private_token", "Bad\nprivate", "A" * 129]
)
def test_invalid_or_absent_sdk_metadata_is_not_logged(monkeypatch, code):
    cloud = RuntimeCloud(region="cn-beijing", credential_file="")
    error = ApiError("private body", error_code=code)
    api = Mock(side_effect=error)
    monkeypatch.setattr(
        cloud, "_client", lambda **kwargs: SimpleNamespace(create_runtime=api)
    )
    events = []
    with diagnostic_scope(events.append), pytest.raises(ApiError):
        asyncio.run(cloud.call("create_runtime", object()))
    assert "errorCode" not in events[-1]
    assert "requestId" not in events[-1]
    assert "private" not in str(events)


def test_success_and_cancel_do_not_emit_failure_diagnostics(monkeypatch):
    cloud = RuntimeCloud(region="cn-beijing", credential_file="")
    response = Mock()
    response.model_dump.return_value = {"RuntimeId": "r-test"}
    api = Mock(return_value=response)
    monkeypatch.setattr(
        cloud, "_client", lambda **kwargs: SimpleNamespace(create_runtime=api)
    )
    events = []
    with diagnostic_scope(events.append):
        assert asyncio.run(cloud.call("create_runtime", object())) == {
            "RuntimeId": "r-test"
        }
    assert events == []
    api.side_effect = asyncio.CancelledError()
    with diagnostic_scope(events.append), pytest.raises(asyncio.CancelledError):
        asyncio.run(cloud.call("create_runtime", object()))
    assert events == []


def test_transport_failure_has_category_and_no_auto_replay(monkeypatch):
    cloud = RuntimeCloud(region="cn-beijing", credential_file="")
    api = Mock(side_effect=TimeoutError("private timeout"))
    monkeypatch.setattr(
        cloud, "_client", lambda **kwargs: SimpleNamespace(update_runtime=api)
    )
    events = []
    with diagnostic_scope(events.append), pytest.raises(TimeoutError):
        asyncio.run(cloud.call("update_runtime", object()))
    assert events[-1]["category"] == "timeout"
    assert api.call_count == 1
    assert "errorCode" not in events[-1]


@pytest.mark.parametrize("method", ["create_runtime", "update_runtime"])
@pytest.mark.parametrize("encoding", ["bytes", "json", "bytes_repr", "body", "http"])
def test_wrapped_sdk_json_rejection_retains_only_identifiers(
    monkeypatch, method, encoding
):
    metadata = {
        "ResponseMetadata": {
            "RequestId": "20261014100728ABCDEF0123456789ABCD",
            "Error": {
                "Code": "InvalidParameter.Runtime",
                "Message": "private secret response",
            },
        },
        "Result": {"ApiKey": "private key"},
    }

    class SDKBodyError(Exception):
        body: str | None = None
        response: object | None = None

    body = json.dumps(metadata)
    inner = SDKBodyError(body.encode() if encoding == "bytes" else body)
    if encoding == "bytes_repr":
        inner = SDKBodyError(str(body.encode()))
    elif encoding == "body":
        inner = SDKBodyError("private wrapper")
        inner.body = body
    elif encoding == "http":
        inner = SDKBodyError("private wrapper")
        inner.response = SimpleNamespace(json=lambda: metadata)
    outer = ApiError("private SDK wrapper")
    outer.__cause__ = inner
    cloud = RuntimeCloud(
        region="ap-southeast-1", provider="byteplus", credential_file=""
    )
    api = Mock(side_effect=outer)
    monkeypatch.setattr(
        cloud, "_client", lambda **kwargs: SimpleNamespace(**{method: api})
    )
    events = []
    with diagnostic_scope(events.append), pytest.raises(ApiError) as caught:
        asyncio.run(cloud.call(method, object()))
    assert caught.value is outer
    assert api.call_count == 1
    assert events[-1]["errorCode"] == "InvalidParameter.Runtime"
    assert events[-1]["requestId"] == metadata["ResponseMetadata"]["RequestId"]
    assert "private" not in str(events)


@pytest.mark.parametrize(
    "argument",
    [
        "private non-JSON response",
        b"not JSON",
        "{'ResponseMetadata': 'private python literal'}",
        "__import__('os').system('private')",
        '{"ResponseMetadata":{"Error":{"Code":"SK_private_token"},"RequestId":"private token"}}',
        'b"invalid bytes representation',
        '{"ResponseMetadata":{"Error":{"Code":"AccessDenied"}}}' + " " * 65536,
        "[" * 1000 + "0" + "]" * 1000,
    ],
)
def test_sdk_argument_decoder_rejects_unsafe_malformed_and_oversized_values(
    monkeypatch, argument
):
    cloud = RuntimeCloud(region="cn-beijing", credential_file="")
    error = ApiError("private wrapper")
    error.__cause__ = Exception(argument)
    api = Mock(side_effect=error)
    monkeypatch.setattr(
        cloud, "_client", lambda **kwargs: SimpleNamespace(create_runtime=api)
    )
    events = []
    with diagnostic_scope(events.append), pytest.raises(ApiError) as caught:
        asyncio.run(cloud.call("create_runtime", object()))
    assert caught.value is error
    assert api.call_count == 1
    assert "errorCode" not in events[-1]
    assert "requestId" not in events[-1]
    assert "private" not in str(events)
