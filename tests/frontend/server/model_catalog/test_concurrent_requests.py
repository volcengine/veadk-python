# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
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
from typing import cast

import pytest

from frontend.server.model_catalog.client import ModelApiKeyClient, ModelCatalogClient
from frontend.server.model_catalog.models import ModelOptionsResponse
from frontend.server.model_catalog.protocol import ModelCatalogError
from frontend.server.model_catalog.service import (
    ModelApiKeyService,
    ModelCatalogService,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["volcengine", "byteplus"])
@pytest.mark.parametrize("status", [200, 429])
async def test_overlapping_forced_refreshes_share_one_cloud_query(provider, status):
    entered = asyncio.Event()
    release = asyncio.Event()

    class Models:
        activation_calls = 0
        model_calls = 0

        async def list_activations(self):
            self.activation_calls += 1
            entered.set()
            await release.wait()
            if status == 429:
                raise ModelCatalogError("rate limited", status_code=429)
            return []

        async def list_models(self):
            self.model_calls += 1
            return []

    models = Models()
    service = ModelCatalogService(
        provider=provider, client=cast(ModelCatalogClient, models)
    )
    pending = [
        asyncio.create_task(service.list_options(force_refresh=True)) for _ in range(5)
    ]
    await entered.wait()
    release.set()
    results = await asyncio.gather(*pending, return_exceptions=True)
    assert models.activation_calls == models.model_calls == 1
    if status == 429:
        assert all(
            isinstance(result, ModelCatalogError) and result.status_code == 429
            for result in results
        )
    # A later user-initiated refresh is a new query, including after an error.
    await asyncio.gather(
        service.list_options(force_refresh=True), return_exceptions=True
    )
    assert models.activation_calls == models.model_calls == 2


@pytest.mark.asyncio
async def test_cancelling_one_caller_does_not_cancel_the_shared_query():
    entered = asyncio.Event()
    release = asyncio.Event()

    class Models:
        calls = 0

        async def list_activations(self):
            self.calls += 1
            entered.set()
            await release.wait()
            return []

        async def list_models(self):
            return []

    models = Models()
    service = ModelCatalogService(
        provider="volcengine", client=cast(ModelCatalogClient, models)
    )
    first = asyncio.create_task(service.list_options())
    second = asyncio.create_task(service.list_options())
    await entered.wait()
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    release.set()
    assert (await second).models == []
    assert models.calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["volcengine", "byteplus"])
async def test_key_list_shares_overlapping_reads_but_fetches_again_after_completion(
    provider,
):
    entered = asyncio.Event()
    release = asyncio.Event()

    class Keys:
        calls = 0

        async def list_keys(self):
            self.calls += 1
            entered.set()
            await release.wait()
            return [{"id": str(self.calls), "name": "latest"}]

    keys = Keys()
    service = ModelApiKeyService(
        provider=provider, client=cast(ModelApiKeyClient, keys)
    )
    pending = [asyncio.create_task(service.list_keys()) for _ in range(5)]
    await entered.wait()
    release.set()
    results = await asyncio.gather(*pending)
    assert keys.calls == 1
    assert all(result.keys[0].id == "1" for result in results)
    assert (await service.list_keys()).keys[0].id == "2"


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["volcengine", "byteplus"])
@pytest.mark.parametrize("concurrency", [1, 5, 20, 100])
async def test_repeated_bursts_recover_after_rate_limits_and_timeouts(
    provider, concurrency
):
    class Models:
        calls = 0
        model_calls = 0
        status = 200
        entered: asyncio.Event
        release: asyncio.Event

        async def list_activations(self):
            self.calls += 1
            self.entered.set()
            await self.release.wait()
            if self.status != 200:
                raise ModelCatalogError(
                    "simulated cloud failure", status_code=self.status
                )
            return []

        async def list_models(self):
            self.model_calls += 1
            return [
                {"id": f"version-{self.model_calls}", "name": "model", "domain": "LLM"}
            ]

    models = Models()
    service = ModelCatalogService(
        provider=provider, client=cast(ModelCatalogClient, models)
    )
    for wave in range(30):
        models.status = [200, 429, 504][wave % 3]
        models.entered = asyncio.Event()
        models.release = asyncio.Event()
        pending = [
            asyncio.create_task(service.list_options(force_refresh=True))
            for _ in range(concurrency)
        ]
        await asyncio.wait_for(models.entered.wait(), timeout=2)
        models.release.set()
        results = await asyncio.wait_for(
            asyncio.gather(*pending, return_exceptions=True), timeout=2
        )
        assert models.calls == models.model_calls == wave + 1
        assert not service._pending_options
        if models.status == 200:
            assert all(
                isinstance(result, ModelOptionsResponse)
                and result.models[0].id == f"version-{wave + 1}"
                for result in results
            )
        else:
            assert all(
                isinstance(result, ModelCatalogError)
                and result.status_code == models.status
                for result in results
            )


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["volcengine", "byteplus"])
@pytest.mark.parametrize("cancel_count", [50, 100])
@pytest.mark.parametrize("status", [200, 429])
async def test_mass_cancellation_does_not_repeat_or_orphan_queries(
    provider, cancel_count, status
):
    entered = asyncio.Event()
    release = asyncio.Event()
    finished = asyncio.Event()
    unhandled = []
    loop = asyncio.get_running_loop()
    previous_handler = loop.get_exception_handler()
    loop.set_exception_handler(lambda _loop, context: unhandled.append(context))

    class Models:
        calls = 0

        async def list_activations(self):
            self.calls += 1
            entered.set()
            await release.wait()
            finished.set()
            if status == 429:
                raise ModelCatalogError("simulated limit", status_code=429)
            return []

        async def list_models(self):
            return []

    try:
        models = Models()
        service = ModelCatalogService(
            provider=provider, client=cast(ModelCatalogClient, models)
        )
        pending = [
            asyncio.create_task(service.list_options(force_refresh=True))
            for _ in range(100)
        ]
        await asyncio.wait_for(entered.wait(), timeout=2)
        for task in pending[:cancel_count]:
            task.cancel()
        release.set()
        results = await asyncio.wait_for(
            asyncio.gather(*pending, return_exceptions=True), timeout=2
        )
        await asyncio.wait_for(finished.wait(), timeout=2)
        # Let completion callbacks release the shared task after every caller cancels.
        for _ in range(3):
            await asyncio.sleep(0)
        assert models.calls == 1
        assert not service._pending_options
        assert (
            sum(isinstance(result, asyncio.CancelledError) for result in results)
            == cancel_count
        )
        assert not unhandled
    finally:
        loop.set_exception_handler(previous_handler)


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["volcengine", "byteplus"])
async def test_repeated_key_list_bursts_never_reuse_an_old_completed_list(provider):
    class Keys:
        calls = 0
        entered: asyncio.Event
        release: asyncio.Event

        async def list_keys(self):
            self.calls += 1
            self.entered.set()
            await self.release.wait()
            return [
                {
                    "id": f"new-key-{self.calls}",
                    "name": "latest",
                    "status": "Active",
                    "allow_all": self.calls % 2 == 0,
                }
            ]

    keys = Keys()
    service = ModelApiKeyService(
        provider=provider, client=cast(ModelApiKeyClient, keys)
    )
    for wave in range(10):
        keys.entered = asyncio.Event()
        keys.release = asyncio.Event()
        pending = [asyncio.create_task(service.list_keys()) for _ in range(100)]
        await asyncio.wait_for(keys.entered.wait(), timeout=2)
        keys.release.set()
        results = await asyncio.wait_for(asyncio.gather(*pending), timeout=2)
        assert keys.calls == wave + 1
        assert service._pending_keys is None
        assert all(result.keys[0].id == f"new-key-{wave + 1}" for result in results)
        assert all(
            result.keys[0].allow_all == ((wave + 1) % 2 == 0) for result in results
        )
