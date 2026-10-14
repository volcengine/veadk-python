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
import copy
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from veadk.integrations.mpa.managed.config import (
    load_studio_profile,
    with_creation_resources,
)
from veadk.integrations.mpa.managed.openviking import (
    OpenVikingCloud,
    OpenVikingError,
    ensure_openviking,
)
from veadk.integrations.mpa.managed.database import agent_suffix


class Entry:
    def __init__(self):
        self.record = {}

    async def read(self):
        return copy.deepcopy(self.record)

    async def save(self, row):
        self.record = copy.deepcopy(row)


def fixture():
    suffix = agent_suffix("account", "ap-southeast-1", "mi-example")
    row = {
        "ResourceID": "ov-example",
        "Status": "READY",
        "Name": "mpa_ov_" + suffix,
        "Description": "mpa-openviking:v1:" + suffix,
        "Project": "default",
        "Version": "developer",
        "Source": "volcengine",
        "VLM": {
            "ModelName": "seed-2-0-lite",
            "Credentials": [
                {"Source": "volcengine", "EndpointID": "seed-2-0-lite-260428"}
            ],
        },
        "Embedding": {
            "ModelName": "skylark-embedding-vision",
            "Credentials": [
                {
                    "Source": "volcengine",
                    "EndpointID": "skylark-embedding-vision-251215",
                }
            ],
        },
    }
    cloud = Mock(
        create=AsyncMock(return_value="ov-example"),
        get=AsyncMock(return_value=row),
        api_key=AsyncMock(return_value="test-library-key"),
    )
    return Entry(), cloud, row


async def ensure(entry, cloud):
    return await ensure_openviking(
        entry,
        cloud,
        account="account",
        region="ap-southeast-1",
        provider="byteplus",
        agent_id="mi-example",
        model_api_key="test-inference-key",
    )


@pytest.fixture(autouse=True)
def isolate_model_environment(monkeypatch):
    for name in ("OV_MODEL_API_KEY", "OV_VLM_ENDPOINT_ID", "OV_EMBEDDING_ENDPOINT_ID"):
        monkeypatch.delenv(name, raising=False)


def test_byteplus_new_profile_advertises_ov_and_preserves_explicit_requests(
    monkeypatch,
):
    profile = load_studio_profile(provider="byteplus")
    assert profile.summary()["openvikingMode"] == "auto"
    assert profile.managed.openviking.mode == "manual"
    assert with_creation_resources(profile, {}).managed.openviking.mode == "manual"
    updated = with_creation_resources(profile, {"openvikingMode": "auto"})
    assert updated.managed.openviking.mode == "auto"
    monkeypatch.setenv("OV_MODEL_API_KEY", "unused-legacy-value")
    assert with_creation_resources(profile, {"openvikingMode": "auto"}) == updated


def test_developer_binding_reuse_and_no_keys_in_registry():
    async def run():
        entry, cloud, row = fixture()
        env = await ensure(entry, cloud)
        assert env == {
            "OPENVIKING_URL": "https://api.vikingdb.ap-southeast-1.bytepluses.com/openviking",
            "OPENVIKING_RESOURCE_ID": "ov-example",
            "OPENVIKING_API_KEY": "test-library-key",
            "OPENVIKING_USER": "default",
        }
        expected = {k: v for k, v in row.items() if k not in {"ResourceID", "Status"}}
        assert cloud.create.await_args.args[0] == expected
        assert await ensure(entry, cloud) == env
        cloud.create.assert_awaited_once()
        assert "test-inference-key" not in json.dumps(entry.record)
        assert "test-library-key" not in json.dumps(entry.record)

    asyncio.run(run())


@pytest.mark.parametrize(
    "field,value",
    [("Version", "enterprise"), ("Source", "codeplan"), ("Status", "FAILED")],
)
def test_readback_conflicts_never_inject_keys(field, value):
    async def run():
        entry, cloud, row = fixture()
        row[field] = value
        with pytest.raises(OpenVikingError):
            await ensure(entry, cloud)
        cloud.api_key.assert_not_awaited()

    asyncio.run(run())


def test_ambiguous_byteplus_create_does_not_duplicate():
    async def run():
        entry, cloud, _ = fixture()
        cloud.create.side_effect = TimeoutError("test-private-value")
        for _ in range(2):
            with pytest.raises(OpenVikingError, match="openvikingCreateUnknown"):
                await ensure(entry, cloud)
        cloud.create.assert_awaited_once()

    asyncio.run(run())


def test_byteplus_wire_path_credentials_and_default_user(monkeypatch):
    async def run():
        source = Mock(provider="byteplus", region="ap-southeast-1")
        source._credentials.return_value = SimpleNamespace(
            access_key_id="test-ak",
            secret_access_key="test-sk",
            session_token="test-sts",
        )
        signed = Mock(return_value={"result": {"ResourceID": "ov-example"}})
        monkeypatch.setattr(
            "veadk.integrations.mpa.managed.openviking_byteplus.signed_request", signed
        )
        cloud = OpenVikingCloud(source)
        _, _, row = fixture()
        request = {k: v for k, v in row.items() if k not in {"ResourceID", "Status"}}
        assert (
            await cloud.create(request, model_api_key="test-inference-key")
            == "ov-example"
        )
        assert signed.call_args.kwargs["action"] == "CreateOpenVikingCollection"
        assert signed.call_args.kwargs["credential"].session_token == "test-sts"
        assert signed.call_args.kwargs["body"]["VLM"]["Credentials"] == [
            {
                "Source": "volcengine",
                "ApiKey": "test-inference-key",
                "EndpointID": "seed-2-0-lite-260428",
            }
        ]
        assert "ApiKey" not in request["VLM"]["Credentials"][0]
        signed.return_value = {
            "Result": {"ApiKey": "test-library-key", "UserID": "default"}
        }
        assert await cloud.api_key("ov-example") == "test-library-key"
        assert signed.call_args.kwargs["body"] == {"ResourceID": "ov-example"}
        signed.return_value = {
            "Result": {"ApiKey": "test-library-key", "UserID": "other"}
        }
        with pytest.raises(OpenVikingError):
            await cloud.api_key("ov-example")

    asyncio.run(run())


@pytest.mark.parametrize("name", ["OV_VLM_ENDPOINT_ID", "OV_EMBEDDING_ENDPOINT_ID"])
@pytest.mark.parametrize("value", ["", "bad value", "https://example.test", "x" * 129])
def test_invalid_endpoint_stops_before_cloud_construction(monkeypatch, name, value):
    from veadk.integrations.mpa.managed.service import provision

    monkeypatch.setenv(name, value)
    profile = load_studio_profile(provider="byteplus")
    with pytest.raises(
        ValueError, match="OV_VLM_ENDPOINT_ID.*OV_EMBEDDING_ENDPOINT_ID"
    ):
        with_creation_resources(profile, {"openvikingMode": "auto"})
    assert with_creation_resources(profile, {}).managed.openviking.mode == "manual"
    profile.managed.openviking.mode = "auto"
    runtime = Mock()
    monkeypatch.setattr("veadk.integrations.mpa.managed.service.RuntimeCloud", runtime)
    with pytest.raises(OpenVikingError, match="openvikingModelEndpointsInvalid"):
        asyncio.run(provision(profile, agent_id="mi-example", owner="test-owner"))
    runtime.assert_not_called()


def test_cancellation_keeps_byteplus_library_for_retry():
    async def run():
        entry, cloud, _ = fixture()
        cloud.get.side_effect = asyncio.CancelledError()
        with pytest.raises(asyncio.CancelledError):
            await ensure(entry, cloud)
        assert entry.record["openviking_id"] == "ov-example"
        cloud.api_key.assert_not_awaited()
        cloud.get.side_effect = None
        await ensure(entry, cloud)
        cloud.create.assert_awaited_once()

    asyncio.run(run())


@pytest.mark.parametrize("token", ["", "test-sts"])
def test_wire_signature_includes_required_headers_and_path(monkeypatch, token):
    import datetime
    import hashlib
    import hmac
    import requests
    from veadk.integrations.mpa.managed import openviking_byteplus as module

    class Clock(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 10, 14, 0, 0, 0, tzinfo=tz)

    monkeypatch.setattr(
        module, "datetime", SimpleNamespace(datetime=Clock, timezone=datetime.timezone)
    )
    response = Mock()
    response.json.return_value = {"Result": {"Status": "READY"}}
    post = Mock(return_value=response)
    monkeypatch.setattr(requests, "post", post)
    credential = SimpleNamespace(
        access_key_id="test-ak", secret_access_key="test-sk", session_token=token
    )
    module.signed_request(
        action="GetOpenVikingCollection",
        body={"ResourceID": "ov-example"},
        credential=credential,
    )
    assert (
        post.call_args.args[0]
        == "https://vikingdb.ap-southeast-1.byteplusapi.com/api/openviking/GetOpenVikingCollection?Action=GetOpenVikingCollection&Version=2025-06-09"
    )
    wire = post.call_args.kwargs
    assert wire["timeout"] == (10, 30)
    assert wire["data"] == '{"ResourceID": "ov-example"}'
    headers = wire["headers"]
    assert headers["X-Top-Service"] == "vikingdb"
    assert headers["X-Top-Region"] == "ap-southeast-1"
    digest = hashlib.sha256(b'{"ResourceID": "ov-example"}').hexdigest()
    names = "content-type;host;x-content-sha256;x-date" + (
        ";x-security-token" if token else ""
    )
    canonical = (
        "POST\n/api/openviking/GetOpenVikingCollection\n"
        "Action=GetOpenVikingCollection&Version=2025-06-09\n"
        "content-type:application/json\nhost:vikingdb.ap-southeast-1.byteplusapi.com\n"
        f"x-content-sha256:{digest}\nx-date:20261014T000000Z"
        + (f"\nx-security-token:{token}" if token else "")
        + f"\n\n{names}\n{digest}"
    )
    scope = "20261014/ap-southeast-1/vikingdb/request"
    to_sign = f"HMAC-SHA256\n20261014T000000Z\n{scope}\n{hashlib.sha256(canonical.encode()).hexdigest()}"
    key = b"test-sk"
    for part in (b"20261014", b"ap-southeast-1", b"vikingdb", b"request"):
        key = hmac.new(key, part, hashlib.sha256).digest()
    signature = hmac.new(key, to_sign.encode(), hashlib.sha256).hexdigest()
    assert (
        headers["Authorization"]
        == f"HMAC-SHA256 Credential=test-ak/{scope}, SignedHeaders={names}, Signature={signature}"
    )
    assert headers.get("x-security-token", "") == token


def test_transport_preserves_safe_provider_error_for_adapter(monkeypatch):
    import requests
    from veadk.integrations.mpa.managed.openviking_byteplus import signed_request

    response = Mock()
    response.json.return_value = {
        "ResponseMetadata": {
            "Error": {"Code": "AccessDenied", "Message": "test-private-provider-value"}
        }
    }
    monkeypatch.setattr(requests, "post", Mock(return_value=response))
    source = Mock(provider="byteplus", region="ap-southeast-1")
    source._credentials.return_value = SimpleNamespace(
        access_key_id="test-ak", secret_access_key="test-sk", session_token=""
    )
    with pytest.raises(OpenVikingError, match="openvikingPermissionDenied") as caught:
        asyncio.run(OpenVikingCloud(source).api_key("ov-example"))
    assert "test-private-provider-value" not in str(caught.value)
    response.json.side_effect = ValueError("bad json")
    response.raise_for_status.side_effect = requests.HTTPError(
        "test-private-http-error"
    )
    with pytest.raises(requests.HTTPError):
        signed_request(
            action="GetOpenVikingCollection", body={}, credential=source._credentials()
        )


def test_endpoint_overrides_are_bound_and_cannot_change_on_retry(monkeypatch):
    async def run():
        entry, cloud, row = fixture()
        monkeypatch.setenv("OV_VLM_ENDPOINT_ID", "ep-vlm-test")
        monkeypatch.setenv("OV_EMBEDDING_ENDPOINT_ID", "ep-embedding-test")
        row["VLM"]["Credentials"][0]["EndpointID"] = "ep-vlm-test"
        row["Embedding"]["Credentials"][0]["EndpointID"] = "ep-embedding-test"
        await ensure(entry, cloud)
        await ensure(entry, cloud)
        cloud.create.assert_awaited_once()
        assert (
            entry.record["openviking_request"]["VLM"]["Credentials"][0]["EndpointID"]
            == "ep-vlm-test"
        )
        monkeypatch.setenv("OV_VLM_ENDPOINT_ID", "ep-other")
        with pytest.raises(OpenVikingError, match="openvikingConfigurationConflict"):
            await ensure(entry, cloud)
        cloud.create.assert_awaited_once()

    asyncio.run(run())


def test_mismatched_remote_endpoint_does_not_inject_key():
    async def run():
        entry, cloud, row = fixture()
        row["Embedding"]["Credentials"][0]["EndpointID"] = "ep-other"
        with pytest.raises(OpenVikingError, match="openvikingConfigurationConflict"):
            await ensure(entry, cloud)
        cloud.api_key.assert_not_awaited()

    asyncio.run(run())


@pytest.mark.parametrize("bound", [False, True])
def test_legacy_coding_intent_never_migrates_or_duplicates(bound):
    async def run():
        entry, cloud, row = fixture()
        request = {k: v for k, v in row.items() if k not in {"ResourceID", "Status"}}
        request["Source"] = "codeplan"
        for field in ("VLM", "Embedding"):
            request[field]["Credentials"] = [{"Source": "codeplan"}]
        entry.record.update(
            openviking_request=request, openviking_create_requested=True
        )
        if bound:
            entry.record.update(openviking_id="ov-existing", openviking_managed=True)
        with pytest.raises(OpenVikingError, match="openvikingConfigurationConflict"):
            await ensure(entry, cloud)
        cloud.create.assert_not_awaited()
        cloud.api_key.assert_not_awaited()

    asyncio.run(run())
