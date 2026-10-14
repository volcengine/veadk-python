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
from unittest.mock import AsyncMock, Mock
from types import SimpleNamespace

import pytest

from veadk.integrations.mpa.managed.database import agent_suffix
from veadk.integrations.mpa.managed.openviking import (
    OpenVikingCloud,
    OpenVikingError,
    ensure_openviking,
)


class Entry:
    def __init__(self):
        self.record = {}

    async def read(self):
        return copy.deepcopy(self.record)

    async def save(self, record):
        self.record = copy.deepcopy(record)


def setup():
    entry = Entry()
    suffix = agent_suffix("account", "cn-beijing", "mi-test")
    row = {
        "ResourceID": "ov-test",
        "Name": "mpa_ov_" + suffix,
        "Description": "mpa-openviking:v1:" + suffix,
        "Project": "default",
        "Version": "enterprise",
        "Status": "READY",
        "VLM": {
            "ModelName": "doubao-seed-2-0-lite",
            "ModelVersion": "260428",
            "Credentials": [
                {"Source": "volcengine", "EndpointID": "doubao-seed-2-0-lite-260428"}
            ],
        },
        "Embedding": {
            "ModelName": "doubao-embedding-vision",
            "ModelVersion": "251215",
            "Credentials": [
                {"Source": "volcengine", "EndpointID": "doubao-embedding-vision-251215"}
            ],
        },
    }
    cloud = Mock()
    cloud.create = AsyncMock(return_value="ov-test")
    cloud.get = AsyncMock(return_value=row)
    cloud.api_key = AsyncMock(return_value="private-test-ov-key")
    return entry, cloud, row


async def ensure(entry, cloud, **kwargs):
    return await ensure_openviking(
        entry,
        cloud,
        account="account",
        region="cn-beijing",
        agent_id="mi-test",
        timeout=10,
        model_api_key=kwargs.pop("model_api_key", "private-test-ark-key"),
        **kwargs,
    )


def test_creation_injects_key_without_persisting_it_and_reuses_library():
    async def run():
        entry, cloud, _ = setup()
        stages = []
        env = await ensure(entry, cloud, progress=stages.append)
        assert env == {
            "OPENVIKING_URL": "https://api.vikingdb.cn-beijing.volces.com/openviking",
            "OPENVIKING_RESOURCE_ID": "ov-test",
            "OPENVIKING_API_KEY": "private-test-ov-key",
            "OPENVIKING_USER": "default",
        }
        request = cloud.create.await_args.args[0]
        assert request["Version"] == "enterprise"
        assert request["VLM"] == {
            "ModelName": "doubao-seed-2.0-lite",
            "ModelVersion": "260428",
            "Credentials": [
                {"Source": "volcengine", "EndpointID": "doubao-seed-2-0-lite-260428"}
            ],
        }
        assert request["Embedding"]["Credentials"] == [
            {"Source": "volcengine", "EndpointID": "doubao-embedding-vision-251215"}
        ]
        assert cloud.create.await_args.kwargs["model_api_key"] == "private-test-ark-key"
        assert "private-test-ark-key" not in json.dumps(entry.record)
        assert "private-test-ov-key" not in json.dumps(entry.record)
        assert entry.record["openviking_id"] == "ov-test"
        assert "openviking" in stages and "openviking_key" in stages
        assert await ensure(entry, cloud) == env
        cloud.create.assert_awaited_once()

    asyncio.run(run())


@pytest.mark.parametrize(
    "change",
    [
        {"Status": "FAILED"},
        {"Status": "UNKNOWN"},
        {"ResourceID": "ov-other"},
        {"Project": "other"},
        {"Description": "unowned"},
        {"Name": "collision"},
        {"VLM": {"ModelName": "unrelated", "ModelVersion": "260428"}},
    ],
)
def test_invalid_library_never_reaches_key_or_runtime(change):
    async def run():
        entry, cloud, row = setup()
        row.update(change)
        with pytest.raises(OpenVikingError):
            await ensure(entry, cloud)
        cloud.api_key.assert_not_awaited()
        assert entry.record["openviking_id"] == "ov-test"

    asyncio.run(run())


def test_ambiguous_create_blocks_duplicate_retry():
    async def run():
        entry, cloud, _ = setup()
        cloud.create.side_effect = TimeoutError("provider secret in exception")
        with pytest.raises(OpenVikingError) as error:
            await ensure(entry, cloud)
        assert error.value.key == "openvikingCreateUnknown"
        assert "secret" not in str(error.value)
        cloud.create.side_effect = None
        with pytest.raises(OpenVikingError) as retry:
            await ensure(entry, cloud)
        assert retry.value.key == "openvikingCreateUnknown"
        cloud.create.assert_awaited_once()

    asyncio.run(run())


def test_proven_rejection_allows_retry_without_default_model_fallback():
    async def run():
        entry, cloud, _ = setup()
        cloud.create.side_effect = OpenVikingError(
            "openvikingModelConfigurationRejected", category="invalid_request"
        )
        with pytest.raises(OpenVikingError):
            await ensure(entry, cloud)
        assert not entry.record["openviking_create_requested"]
        cloud.create.side_effect = None
        await ensure(entry, cloud)
        assert cloud.create.await_count == 2

    asyncio.run(run())


def test_cancellation_retains_binding_and_stops_key_read():
    async def run():
        entry, cloud, _ = setup()
        cloud.get.side_effect = asyncio.CancelledError()
        with pytest.raises(asyncio.CancelledError):
            await ensure(entry, cloud)
        assert entry.record["openviking_id"] == "ov-test"
        cloud.api_key.assert_not_awaited()
        cloud.get.side_effect = None
        await ensure(entry, cloud)
        cloud.create.assert_awaited_once()

    asyncio.run(run())


def test_poll_waits_for_ready_and_times_out_without_reading_key(monkeypatch):
    async def run():
        entry, cloud, row = setup()
        cloud.get.side_effect = [{**row, "Status": "INIT"}, row]
        sleep = AsyncMock()
        monkeypatch.setattr(
            "veadk.integrations.mpa.managed.openviking.asyncio.sleep", sleep
        )
        await ensure(entry, cloud)
        sleep.assert_awaited_once()
        cloud.get.side_effect = None
        cloud.get.return_value = {**row, "Status": "INIT"}
        cloud.api_key.reset_mock()
        clock = Mock(side_effect=[0, 11])
        monkeypatch.setattr(
            "veadk.integrations.mpa.managed.openviking.time",
            SimpleNamespace(monotonic=clock),
        )
        with pytest.raises(OpenVikingError) as error:
            await ensure(entry, cloud)
        assert error.value.key == "openvikingNotReady"
        cloud.api_key.assert_not_awaited()

    asyncio.run(run())


def test_deleted_agent_never_creates_library():
    async def run():
        entry, cloud, _ = setup()
        entry.record["state"] = "deleted"
        with pytest.raises(OpenVikingError):
            await ensure(entry, cloud)
        cloud.create.assert_not_awaited()

    asyncio.run(run())


def test_adapter_uses_current_sts_and_safe_errors(monkeypatch):
    from veadk.integrations.mpa.managed.credentials import Credentials

    async def run():
        source = Mock()
        source.provider = "volcengine"
        source.region = "cn-beijing"
        source._credentials.return_value = Credentials(
            "test-ak", "test-sk", "test-session"
        )
        signed = Mock(
            return_value={"Result": {"ResourceID": "ov-test", "Success": True}}
        )
        monkeypatch.setattr(
            "veadk.utils.volcengine_sign.volcengine_signed_request",
            signed,
        )
        cloud = OpenVikingCloud(source)
        assert (
            await cloud.create(
                {
                    "Name": "mpa_test",
                    "VLM": {
                        "Credentials": [
                            {"Source": "volcengine", "EndpointID": "model-vlm"}
                        ]
                    },
                    "Embedding": {
                        "Credentials": [
                            {"Source": "volcengine", "EndpointID": "model-embedding"}
                        ]
                    },
                },
                model_api_key="private-test-ark-key",
            )
            == "ov-test"
        )
        assert (
            signed.call_args.kwargs["host"] == "vikingdb.cn-beijing.volcengineapi.com"
        )
        assert signed.call_args.kwargs["header"]["X-Security-Token"] == "test-session"
        signed.return_value = {
            "ResponseMetadata": {
                "Error": {"Code": "AccessDenied", "Message": "private-provider-key"}
            }
        }
        with pytest.raises(OpenVikingError) as error:
            await cloud.api_key("ov-test")
        assert error.value.key == "openvikingPermissionDenied"
        assert "private-provider-key" not in str(error.value)
        signed.return_value = {"Result": {"ApiKey": "***"}}
        with pytest.raises(OpenVikingError):
            await cloud.api_key("ov-test")

    asyncio.run(run())


@pytest.mark.parametrize(
    "provider,region", [("byteplus", "ap-southeast-1"), ("volcengine", "cn-shanghai")]
)
def test_adapter_rejects_unsupported_scope(provider, region):
    with pytest.raises(OpenVikingError):
        OpenVikingCloud(Mock(provider=provider, region=region))


@pytest.mark.parametrize("key", ["", "***", "<KEY>", "has space", None])
def test_invalid_model_key_never_dispatches_or_records_intent(key):
    async def run():
        entry, cloud, _ = setup()
        with pytest.raises(OpenVikingError):
            await ensure(entry, cloud, model_api_key=key)
        cloud.create.assert_not_awaited()
        assert entry.record == {}

    asyncio.run(run())


def test_wire_key_is_added_only_to_copy_and_never_to_intent(monkeypatch):
    async def run():
        entry, cloud, _ = setup()
        await ensure(entry, cloud)
        request = copy.deepcopy(entry.record["openviking_request"])
        saved = copy.deepcopy(request)
        source = Mock(provider="volcengine", region="cn-beijing")
        source._credentials.return_value = SimpleNamespace(
            access_key_id="test-ak",
            secret_access_key="test-sk",
            session_token="test-token",
        )
        signed = Mock(
            return_value={"Result": {"ResourceID": "ov-test", "Success": True}}
        )
        monkeypatch.setattr(
            "veadk.utils.volcengine_sign.volcengine_signed_request",
            signed,
        )
        await OpenVikingCloud(source).create(
            request, model_api_key="private-test-ark-key"
        )
        assert request == saved
        for field in ("VLM", "Embedding"):
            credentials = signed.call_args.kwargs["request_body"][field]["Credentials"]
            assert credentials[0]["ApiKey"] == "private-test-ark-key"
            assert credentials[0]["Source"] == "volcengine"
        assert "private-test-ark-key" not in json.dumps(entry.record)

    asyncio.run(run())


@pytest.mark.parametrize(
    "requested,ident,pending,changed,allowed",
    [
        (False, "", False, False, True),
        (True, "", False, False, False),
        (None, "", False, False, False),
        (False, "ov-registered", False, False, False),
        (False, "", True, False, False),
        (False, "", False, True, False),
    ],
)
def test_only_proven_rejected_legacy_intent_can_be_upgraded(
    requested, ident, pending, changed, allowed
):
    async def run():
        entry, cloud, row = setup()
        old = {
            k: copy.deepcopy(v)
            for k, v in row.items()
            if k not in ("ResourceID", "Status")
        }
        old["VLM"]["ModelName"] = "doubao-seed-2.0-lite"
        for field in ("VLM", "Embedding"):
            old[field].pop("Credentials")
        if changed:
            old["Project"] = "other"
        entry.record = {
            "openviking_request": old,
            "openviking_create_requested": requested,
            "pending": pending,
        }
        if ident:
            entry.record.update(openviking_id=ident, openviking_managed=True)
        before = copy.deepcopy(entry.record)
        if allowed:
            await ensure(entry, cloud)
            assert entry.record["openviking_id"] == "ov-test"
            assert entry.record["openviking_request"]["Name"] == old["Name"]
            cloud.create.assert_awaited_once()
        else:
            with pytest.raises(OpenVikingError):
                await ensure(entry, cloud)
            cloud.create.assert_not_awaited()
            assert entry.record == before

    asyncio.run(run())


def test_changed_model_source_does_not_reuse_library():
    async def run():
        entry, cloud, row = setup()
        row["VLM"]["Credentials"][0]["Source"] = "codeplan"
        with pytest.raises(OpenVikingError):
            await ensure(entry, cloud)
        cloud.api_key.assert_not_awaited()

    asyncio.run(run())
