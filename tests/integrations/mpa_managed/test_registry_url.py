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

"""Registry URLs must work with the independently released asyncpg consumer."""

import asyncio
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from tests.integrations.mpa_managed.test_agent_deployment import deployer, template
from veadk.integrations.mpa.managed import runtime
from veadk.integrations.mpa.managed.database import DeploymentError


@pytest.mark.parametrize("mode", ["require", "verify-ca", "verify-full"])
def test_runtime_registry_url_uses_supported_driver_arguments(mode):
    url = f"postgresql://user:fake%40pass@registry.example/admin?sslmode={mode}&timeout=10"
    normalized = runtime.asyncpg_registry_url(url)
    parsed = make_url(normalized)
    assert parsed.password == "fake@pass"
    assert parsed.query == {"ssl": mode, "timeout": "10"}
    engine = create_async_engine(parsed.set(drivername="postgresql+asyncpg"))
    _, arguments = engine.dialect.create_connect_args(engine.url)
    assert arguments["ssl"] == mode and "sslmode" not in arguments
    asyncio.run(engine.dispose())


@pytest.mark.parametrize("query", ["", "?ssl=require", "?timeout=10"])
def test_compatible_registry_url_is_unchanged(query):
    url = "postgresql://user:fake@registry.example/admin" + query
    assert runtime.asyncpg_registry_url(url) == url


@pytest.mark.parametrize(
    "query",
    [
        "sslmode=require&ssl=disable",
        "sslmode=require&sslmode=disable",
        "ssl=require&ssl=disable",
    ],
)
def test_conflicting_or_repeated_tls_parameters_fail_without_secret(query):
    with pytest.raises(DeploymentError) as error:
        runtime.asyncpg_registry_url(
            "postgresql://user:fake-secret@registry.example/admin?" + query
        )
    assert "fake-secret" not in str(error.value)


def test_initial_and_final_payloads_use_compatible_registry_url():
    async def run():
        svc, _, cloud, _ = deployer()
        svc.shared_url = "postgresql://user:fake@registry.example/admin?sslmode=require"
        await svc.deploy(template())
        for payload in [*cloud.creates, *cloud.updates]:
            url = runtime.env_map(payload)["SHARED_APIG_DATABASE_URL"]
            assert make_url(url).query == {"ssl": "require"}

    asyncio.run(run())


@pytest.mark.parametrize("lost_response", [False, True])
def test_legacy_pending_registry_url_resumes_without_replacing_resources(
    monkeypatch, lost_response
):
    async def run():
        svc, registry, cloud, _ = deployer()
        svc.shared_url = "postgresql://user:fake@registry.example/admin?sslmode=require"
        with monkeypatch.context() as legacy:
            legacy.setattr(runtime, "asyncpg_registry_url", lambda value: value)
            if lost_response:
                cloud.lose_create_response = True
            else:
                legacy.setattr(
                    svc, "wait_platform", AsyncMock(side_effect=TimeoutError)
                )
            with pytest.raises(TimeoutError):
                await svc.deploy(template())
        first = cloud.creates[0]
        changed = template()
        changed["ArtifactUrl"] = "different:image"
        with pytest.raises(DeploymentError, match="unfinished"):
            await svc.deploy(changed)
        result = await svc.deploy(template())
        assert result["state"] == "ready" and not registry.row["pending"]
        assert len(cloud.runtimes) == len(cloud.space_creates) == 1
        assert len(cloud.creates) == (2 if lost_response else 1)
        if lost_response:
            assert cloud.creates[1] == first
        assert make_url(
            runtime.env_map(cloud.updates[-1])["SHARED_APIG_DATABASE_URL"]
        ).query == {"ssl": "require"}

    asyncio.run(run())
