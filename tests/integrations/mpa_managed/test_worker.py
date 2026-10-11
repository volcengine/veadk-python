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
import hashlib
import json
from unittest.mock import AsyncMock

import pytest

from tests.integrations.mpa_managed.test_agent_deployment import Registry
from veadk.integrations.mpa.managed.config import Worker, load_studio_profile
from veadk.integrations.mpa.managed.config import ConfigurationError
from veadk.integrations.mpa.managed.database import DeploymentError, agent_suffix
from veadk.integrations.mpa.managed.worker import (
    WorkerCloud,
    _missing_worker_metadata,
    ensure_worker,
)


def test_studio_worker_creation_needs_no_reference_in_new_account(monkeypatch):
    monkeypatch.setenv("VEADK_MPA_CONFIG_MODEL_AGENT_API_KEY", "test-model-key")
    profile = load_studio_profile()

    async def run():
        cloud = AsyncMock()
        cloud.get.side_effect = AssertionError("unexpected reference lookup")
        cloud.find.return_value = []
        cloud.create.side_effect = DeploymentError("request captured")
        registry = Registry()
        with pytest.raises(DeploymentError, match="request captured"):
            await ensure_worker(
                registry,
                cloud,
                profile.managed.worker,
                account="new-account",
                region="cn-beijing",
                agent_id="mi-new-agent",
            )
        cloud.get.assert_not_awaited()
        request = cloud.create.call_args.args[0]
        env = {item["Key"]: item["Value"] for item in request["Envs"]}
        assert env == {"MPA_AGENT_ID": "mi-new-agent"}
        assert request["Port"] == 8000
        assert request["ImageUrl"] == profile.managed.worker.image
        assert request["RoleName"] == profile.managed.worker.role_name
        assert "test-model-key" not in json.dumps(request)
        assert "Envs" not in registry.row
        assert "env" not in registry.row
        assert "MPA_AGENT_ID" not in profile.managed.worker.env

    asyncio.run(run())


def test_worker_explicit_environment_overrides_reference_without_mutation():
    async def run():
        source = {
            "Envs": [
                {"Key": "SETTING", "Value": "inherited"},
                {"Key": "KEEP", "Value": "keep"},
                {"Key": "MPA_AGENT_ID", "Value": "old-agent"},
                {"Key": "FEISHU_APP_SECRET", "Value": "old-secret"},
                {"Key": "SHARED_APIG_DATABASE_URL", "Value": "old-control-url"},
            ]
        }
        before = json.dumps(source)
        cloud = AsyncMock()
        cloud.get.return_value = source
        cloud.find.return_value = []
        cloud.create.side_effect = DeploymentError("request captured")
        options = Worker(
            image="worker:v1", reference_id="t-reference", env={"SETTING": "explicit"}
        )
        with pytest.raises(DeploymentError, match="request captured"):
            await ensure_worker(
                Registry(), cloud, options, account="a", region="r", agent_id="agent"
            )
        cloud.get.assert_awaited_once_with("t-reference")
        request = cloud.create.call_args.args[0]
        assert {item["Key"]: item["Value"] for item in request["Envs"]} == {
            "SETTING": "explicit",
            "KEEP": "keep",
            "MPA_AGENT_ID": "agent",
        }
        assert options.env == {"SETTING": "explicit"}
        assert json.dumps(source) == before

    asyncio.run(run())


def test_unfinished_worker_environment_preserves_token_and_rejects_changes():
    async def run():
        registry = Registry()
        cloud = AsyncMock()
        cloud.find.return_value = []
        cloud.create.side_effect = DeploymentError("response lost")
        options = Worker(image="worker:v1", env={"SETTING": "original"})
        for _ in range(2):
            with pytest.raises(DeploymentError, match="response lost"):
                await ensure_worker(
                    registry, cloud, options, account="a", region="r", agent_id="agent"
                )
        assert cloud.create.call_args_list[0] == cloud.create.call_args_list[1]
        cloud.reset_mock()
        token, digest = registry.row["worker_token"], registry.row["worker_hash"]
        with pytest.raises(DeploymentError, match="configuration changed"):
            await ensure_worker(
                registry,
                cloud,
                Worker(image="worker:v1", env={"SETTING": "changed"}),
                account="a",
                region="r",
                agent_id="agent",
            )
        cloud.find.assert_not_awaited()
        cloud.create.assert_not_awaited()
        assert registry.row["worker_token"] == token
        assert registry.row["worker_hash"] == digest
        assert "original" not in json.dumps(registry.row)

    asyncio.run(run())


@pytest.mark.parametrize("agent_id", ["mi-example-id", " mi-example-id "])
def test_new_worker_uses_agent_derived_name(agent_id):
    async def run():
        cloud = AsyncMock()
        cloud.find.return_value = []
        cloud.create.side_effect = DeploymentError("stop after request capture")
        with pytest.raises(DeploymentError, match="request capture"):
            await ensure_worker(
                Registry(),
                cloud,
                Worker(image="worker:v1"),
                account="a",
                region="r",
                agent_id=agent_id,
            )
        request = cloud.create.call_args.args[0]
        assert request["Name"] == "mi_example_id"
        cloud.find.assert_awaited_once_with("mi_example_id")
        assert {item["Key"]: item["Value"] for item in request["Tags"]}[
            "mpa_agent_key"
        ] == agent_suffix("a", "r", agent_id)
        assert {item["Key"]: item["Value"] for item in request["Envs"]}[
            "MPA_AGENT_ID"
        ] == agent_id

    asyncio.run(run())


@pytest.mark.parametrize("name", [" Support-Agent_01 ", "a" * 64])
def test_named_worker_preserves_entered_name_and_internal_bindings(name):
    async def run():
        cloud = AsyncMock()
        cloud.find.return_value = []
        cloud.create.side_effect = DeploymentError("request captured")
        registry = Registry()
        with pytest.raises(DeploymentError, match="request captured"):
            await ensure_worker(
                registry,
                cloud,
                Worker(image="worker:v1"),
                account="a",
                region="r",
                agent_id="mi-internal",
                runtime_name=name,
            )
        request = cloud.create.call_args.args[0]
        assert request["Name"] == name.strip()
        cloud.find.assert_awaited_once_with(name.strip())
        assert registry.row["worker_name"] == name.strip()
        assert {item["Key"]: item["Value"] for item in request["Envs"]} == {
            "MPA_AGENT_ID": "mi-internal",
        }
        assert {item["Key"]: item["Value"] for item in request["Tags"]}[
            "mpa_agent_key"
        ] == agent_suffix("a", "r", "mi-internal")

    asyncio.run(run())


@pytest.mark.parametrize("name", ["abc", "a" * 65, "bad/name", "中文名称"])
def test_invalid_worker_name_fails_before_cloud_calls(name):
    async def run():
        cloud = AsyncMock()
        with pytest.raises(ConfigurationError):
            await ensure_worker(
                Registry(),
                cloud,
                Worker(image="worker:v1"),
                account="a",
                region="r",
                agent_id="mi-internal",
                runtime_name=name,
            )
        cloud.get.assert_not_awaited()
        cloud.find.assert_not_awaited()
        cloud.create.assert_not_awaited()

    asyncio.run(run())


@pytest.mark.parametrize("previous_name", ["mi_internal", "mpa_worker_hash"])
@pytest.mark.parametrize("discovered", [False, True])
@pytest.mark.parametrize("changed_image", [False, True])
def test_named_worker_replays_pre_upgrade_name(
    previous_name, discovered, changed_image
):
    async def run():
        from tests.integrations.mpa_managed.test_worker_recovery import ready

        registry = Registry()
        cloud = AsyncMock()
        cloud.find.return_value = []
        cloud.create.side_effect = DeploymentError("response lost")
        options = Worker(image="worker:v1")
        with pytest.raises(DeploymentError, match="response lost"):
            await ensure_worker(
                registry,
                cloud,
                options,
                account="a",
                region="r",
                agent_id="agent",
                runtime_name="Support-Agent_01",
            )
        previous = dict(cloud.create.call_args.args[0])
        token = previous.pop("ClientToken")
        previous["Name"] = (
            "agent"
            if previous_name == "mi_internal"
            else "mpa_worker_" + agent_suffix("a", "r", "agent")
        )
        registry.row.pop("worker_name")
        registry.row["worker_hash"] = hashlib.sha256(
            json.dumps(previous, sort_keys=True).encode()
        ).hexdigest()
        cloud.reset_mock()
        cloud.find.return_value = [ready()] if discovered else []
        cloud.create.side_effect = None
        cloud.create.return_value = "t-test"
        cloud.get.return_value = ready()
        if changed_image:
            with pytest.raises(DeploymentError, match="configuration changed"):
                await ensure_worker(
                    registry,
                    cloud,
                    Worker(image="worker:v2"),
                    account="a",
                    region="r",
                    agent_id="agent",
                    runtime_name="Support-Agent_01",
                )
            cloud.find.assert_not_awaited()
            cloud.create.assert_not_awaited()
        else:
            if not discovered:
                cloud.create.side_effect = DeploymentError("response lost")
                for _ in range(2):
                    with pytest.raises(DeploymentError, match="response lost"):
                        await ensure_worker(
                            registry,
                            cloud,
                            options,
                            account="a",
                            region="r",
                            agent_id="agent",
                            runtime_name="Support-Agent_01",
                        )
                    assert cloud.create.call_args.args[0] == {
                        **previous,
                        "ClientToken": token,
                    }
                    assert "worker_name" not in registry.row
                cloud.reset_mock()
                cloud.create.side_effect = None
            assert (
                await ensure_worker(
                    registry,
                    cloud,
                    options,
                    account="a",
                    region="r",
                    agent_id="agent",
                    runtime_name="Support-Agent_01",
                )
                == "t-test"
            )
            cloud.find.assert_awaited_once_with(previous["Name"])
            if discovered:
                cloud.create.assert_not_awaited()
            else:
                cloud.create.assert_awaited_once_with(
                    {**previous, "ClientToken": token}
                )
        assert registry.row["worker_token"] == token

    asyncio.run(run())


def test_named_pending_worker_retries_exact_request_and_rejects_name_change():
    async def run():
        registry = Registry()
        cloud = AsyncMock()
        cloud.find.return_value = []
        cloud.create.side_effect = DeploymentError("response lost")
        for _ in range(2):
            with pytest.raises(DeploymentError, match="response lost"):
                await ensure_worker(
                    registry,
                    cloud,
                    Worker(image="worker:v1"),
                    account="a",
                    region="r",
                    agent_id="mi-internal",
                    runtime_name="Support-Agent_01",
                )
        assert cloud.create.call_args_list[0] == cloud.create.call_args_list[1]
        token, digest = registry.row["worker_token"], registry.row["worker_hash"]
        cloud.reset_mock()
        for name in ["changed-name", "mi_internal", ""]:
            with pytest.raises(DeploymentError, match="configuration changed"):
                await ensure_worker(
                    registry,
                    cloud,
                    Worker(image="worker:v1"),
                    account="a",
                    region="r",
                    agent_id="mi-internal",
                    runtime_name=name,
                )
        cloud.find.assert_not_awaited()
        cloud.create.assert_not_awaited()
        assert registry.row["worker_token"] == token
        assert registry.row["worker_hash"] == digest

    asyncio.run(run())


def test_unrelated_tool_with_entered_name_is_not_adopted():
    async def run():
        cloud = AsyncMock()
        cloud.find.return_value = [{"ToolId": "t-unrelated", "Name": "support-agent"}]
        with pytest.raises(DeploymentError, match="name collision"):
            await ensure_worker(
                Registry(),
                cloud,
                Worker(image="worker:v1"),
                account="a",
                region="r",
                agent_id="mi-internal",
                runtime_name="support-agent",
            )
        cloud.create.assert_not_awaited()
        cloud.get.assert_not_awaited()

    asyncio.run(run())


@pytest.mark.parametrize("discovered", [False, True])
@pytest.mark.parametrize("changed_image", [False, True])
def test_unfinished_legacy_worker_retains_request_and_token(discovered, changed_image):
    async def run():
        from tests.integrations.mpa_managed.test_worker_recovery import ready

        registry = Registry()
        cloud = AsyncMock()
        cloud.find.return_value = []
        cloud.create.side_effect = DeploymentError("response lost")
        options = Worker(image="worker:v1")
        with pytest.raises(DeploymentError, match="response lost"):
            await ensure_worker(
                registry, cloud, options, account="a", region="r", agent_id="agent"
            )
        # Model a durable pre-upgrade intent whose provider response was lost.
        previous_request = dict(cloud.create.call_args.args[0])
        token = previous_request.pop("ClientToken")
        previous_request["Name"] = "mpa_worker_" + agent_suffix("a", "r", "agent")
        registry.row.pop("worker_name")
        registry.row["worker_hash"] = hashlib.sha256(
            json.dumps(previous_request, sort_keys=True).encode()
        ).hexdigest()
        previous_hash = registry.row["worker_hash"]
        cloud.reset_mock()
        cloud.find.return_value = [ready()] if discovered else []
        cloud.create.side_effect = None
        cloud.create.return_value = "t-test"
        cloud.get.return_value = ready()
        if changed_image:
            options = Worker(image="worker:v2")
            with pytest.raises(DeploymentError, match="configuration changed"):
                await ensure_worker(
                    registry, cloud, options, account="a", region="r", agent_id="agent"
                )
            cloud.find.assert_not_awaited()
            cloud.create.assert_not_awaited()
        else:
            assert (
                await ensure_worker(
                    registry, cloud, options, account="a", region="r", agent_id="agent"
                )
                == "t-test"
            )
            cloud.find.assert_awaited_once_with(previous_request["Name"])
            if discovered:
                cloud.create.assert_not_awaited()
            else:
                cloud.create.assert_awaited_once_with(
                    {**previous_request, "ClientToken": token}
                )
        assert registry.row["worker_token"] == token
        assert registry.row["worker_hash"] == previous_hash

    asyncio.run(run())


@pytest.mark.parametrize("registered", [False, True])
def test_existing_worker_id_is_reused_without_name_discovery(registered):
    async def run():
        from tests.integrations.mpa_managed.test_worker_recovery import ready

        registry = Registry()
        if registered:
            registry.row.update(worker_id="t-test", worker_managed=True)
        cloud = AsyncMock()
        cloud.get.return_value = {**ready(), "Name": "mpa_worker_previous"}
        options = (
            Worker(image="worker:v1") if registered else Worker(existing_id="t-test")
        )
        assert (
            await ensure_worker(
                registry,
                cloud,
                options,
                account="a",
                region="r",
                agent_id="agent",
                runtime_name="Support-Agent_01",
            )
            == "t-test"
        )
        cloud.find.assert_not_awaited()
        cloud.create.assert_not_awaited()

    asyncio.run(run())


def test_lost_worker_response_reuses_token_and_scoped_identity(monkeypatch):
    from veadk.integrations.mpa.managed import diagnostics

    monkeypatch.setattr(diagnostics.asyncio, "sleep", AsyncMock())

    async def run():
        registry = Registry()
        cloud = AsyncMock()
        cloud.find.return_value = []
        cloud.create.side_effect = TimeoutError()
        options = Worker(image="registry.example/worker:v1")
        with pytest.raises(TimeoutError):
            await ensure_worker(
                registry, cloud, options, account="a", region="r", agent_id="agent"
            )
        token = registry.row["worker_token"]
        with pytest.raises(TimeoutError):
            await ensure_worker(
                registry, cloud, options, account="a", region="r", agent_id="agent"
            )
        assert [c.args[0]["ClientToken"] for c in cloud.create.call_args_list] == [
            token
        ] * 8
        assert "Envs" not in str(registry.row)

    asyncio.run(run())


def test_worker_ownership_collision_stops_before_creation():
    async def run():
        cloud = AsyncMock()
        cloud.find.return_value = [{"ToolId": "t-other", "Tags": []}]
        with pytest.raises(DeploymentError):
            await ensure_worker(
                Registry(),
                cloud,
                Worker(image="worker:v1"),
                account="a",
                region="r",
                agent_id="agent",
            )
        cloud.create.assert_not_called()

    asyncio.run(run())


def test_managed_worker_create_includes_tos_output_mount():
    async def run():
        registry = Registry()
        cloud = AsyncMock()
        cloud.find.return_value = []
        cloud.create.return_value = "t-created"
        cloud.get.return_value = {
            "ToolId": "t-created",
            "ProjectName": "default",
            "Status": "Ready",
            "Tags": [
                {"Key": "managed_by", "Value": "mpa-deployment"},
                {
                    "Key": "mpa_agent_key",
                    "Value": agent_suffix("a", "r", "agent"),
                },
            ],
            "Envs": [{"Key": "MPA_AGENT_ID", "Value": "agent"}],
            "TosMountConfig": {
                "EnableTos": True,
                "MountPoints": [
                    {
                        "BucketName": "mpa-output",
                        "BucketPath": "/",
                        "Endpoint": "http://tos-r.ivolces.com",
                        "LocalMountPath": "/data/output",
                        "ReadOnly": False,
                    }
                ],
            },
        }
        options = Worker(
            image="worker:v1",
            tos_access_key="tos-ak",
            tos_secret_key="tos-sk",
            tos_bucket="mpa-output",
        )

        assert (
            await ensure_worker(
                registry,
                cloud,
                options,
                account="a",
                region="r",
                agent_id="agent",
            )
            == "t-created"
        )
        request = cloud.create.await_args.args[0]
        config = request["TosMountConfig"]
        assert config["Credentials"] == {
            "AccessKeyId": "tos-ak",
            "SecretAccessKey": "tos-sk",
        }
        assert config["MountPoints"][0]["LocalMountPath"] == "/data/output"
        assert "tos-ak" not in str(registry.row)
        assert "tos-sk" not in str(registry.row)

    asyncio.run(run())


def test_worker_tos_metadata_mismatch_fails_closed():
    expected = {
        "EnableTos": True,
        "MountPoints": [
            {
                "BucketName": "mpa-output",
                "BucketPath": "/",
                "Endpoint": "http://tos-r.ivolces.com",
                "LocalMountPath": "/data/output",
                "ReadOnly": False,
            }
        ],
    }

    with pytest.raises(DeploymentError, match="TOS output mount"):
        _missing_worker_metadata(
            {"TosMountConfig": {"EnableTos": True, "MountPoints": []}},
            tool_id="t-one",
            project="default",
            owned={"managed_by": "mpa-deployment", "mpa_agent_key": "key"},
            agent_id="agent",
            managed=True,
            expected_tos=expected,
        )


def test_worker_discovery_follows_cursor_even_after_short_page():
    cloud = WorkerCloud(None)
    target = {"Name": "target", "ToolId": "target-id"}
    cloud.call = AsyncMock(
        side_effect=[
            {"Tools": [{"Name": "other", "ToolId": "other-id"}], "NextToken": "next"},
            {"Tools": [target]},
        ]
    )
    assert asyncio.run(cloud.find("target")) == [target]
    assert [call.kwargs for call in cloud.call.call_args_list] == [
        {"MaxResults": 100},
        {"MaxResults": 100, "NextToken": "next"},
    ]


def test_worker_discovery_stops_on_full_final_page():
    cloud = WorkerCloud(None)
    cloud.call = AsyncMock(return_value={"Tools": [{"Name": "other"}] * 100})
    assert asyncio.run(cloud.find("target")) == []
    cloud.call.assert_awaited_once()


def test_worker_discovery_deduplicates_ids_but_retains_distinct_name_collisions():
    cloud = WorkerCloud(None)
    first = {"Name": "target", "ToolId": "one"}
    second = {"Name": "target", "ToolId": "two"}
    cloud.call = AsyncMock(
        side_effect=[
            {"Tools": [first], "NextToken": "next"},
            {"Tools": [first, second]},
        ]
    )
    assert asyncio.run(cloud.find("target")) == [first, second]


def test_worker_discovery_rejects_repeated_cursor_without_partial_matches():
    cloud = WorkerCloud(None)
    cloud.call = AsyncMock(
        side_effect=[
            {"Tools": [{"Name": "target", "ToolId": "one"}], "NextToken": "same"},
            {"Tools": [], "NextToken": "same"},
        ]
    )
    with pytest.raises(DeploymentError, match="repeated pagination token"):
        asyncio.run(cloud.find("target"))
    assert cloud.call.await_count == 2


def test_worker_discovery_rejects_page_limit_without_partial_matches():
    cloud = WorkerCloud(None)
    cloud.call = AsyncMock(
        side_effect=[{"Tools": [], "NextToken": str(i)} for i in range(1000)]
    )
    with pytest.raises(DeploymentError, match="pagination limit"):
        asyncio.run(cloud.find("target"))
    assert cloud.call.await_count == 1000


def test_worker_discovery_propagates_provider_failure():
    cloud = WorkerCloud(None)
    cloud.call = AsyncMock(
        side_effect=[{"Tools": [], "NextToken": "next"}, TimeoutError()]
    )
    with pytest.raises(TimeoutError):
        asyncio.run(cloud.find("target"))
