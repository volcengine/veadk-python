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
from unittest.mock import Mock

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from frontend.server.quality.errors import QualityGenerationError
from frontend.server.quality.models import GenerateRequest, GeneratedDatasetBatch
from frontend.server.quality.routes import mount_quality_routes
from frontend.server.quality.service import QualityGenerationService


def request(count=100):
    return GenerateRequest.model_validate(
        dict(
            agent={"name": "orders"},
            preference="balanced",
            scenario="Order lookup",
            requirements="Use the correct order",
            count=count,
        )
    )


def batch(body):
    return GeneratedDatasetBatch.model_validate(
        dict(
            name="Orders",
            description="Order coverage",
            items=[
                {
                    "name": f"Case {index + 1}",
                    "scenario": "Order lookup",
                    "input": f"Order {index}",
                    "expectedOutput": "Correct order",
                    "trajectory": [],
                    "checks": ["Correct ID"],
                }
                for index in range(body.batchStart, body.batchStart + body.batchCount)
            ],
        )
    )


def test_dataset_batches_are_bounded_parallel_and_merged_in_order(monkeypatch):
    async def check():
        active = 0
        peak = 0
        started = []
        four_started = asyncio.Event()
        release = asyncio.Event()
        keys = Mock(return_value="test-key")
        service = QualityGenerationService("volcengine", keys)

        async def generate(body, schema, instruction, *, api_key):
            nonlocal active, peak
            assert api_key == "test-key"
            assert 1 <= body.batchCount <= 20
            assert body.count == 77
            active += 1
            peak = max(peak, active)
            started.append(body.batchStart)
            if active == 4:
                four_started.set()
            await release.wait()
            active -= 1
            return batch(body)

        monkeypatch.setattr(service, "_generate", generate)
        task = asyncio.create_task(service.generate(request(77)))
        await asyncio.wait_for(four_started.wait(), timeout=1)
        assert started == [0, 20, 40, 60]
        release.set()
        result = await task
        assert peak == 4
        assert [item.input for item in result.items] == [
            f"Order {i}" for i in range(77)
        ]
        keys.assert_called_once()

    asyncio.run(check())


def test_dataset_cancellation_cancels_active_and_queued_batches(monkeypatch):
    async def check():
        service = QualityGenerationService("byteplus", Mock(return_value="test-key"))
        started = []
        cancelled = []
        ready = asyncio.Event()

        async def generate(body, *args, **kwargs):
            started.append(body.batchStart)
            if len(started) == 4:
                ready.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.append(body.batchStart)

        monkeypatch.setattr(service, "_generate", generate)
        task = asyncio.create_task(service.generate(request(300)))
        await asyncio.wait_for(ready.wait(), timeout=1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert len(started) == 4
        assert set(cancelled) == set(started)

    asyncio.run(check())


def test_dataset_deadline_preserves_already_returned_provider_errors(monkeypatch):
    monkeypatch.setattr(
        "frontend.server.quality.service.dataset_generation_timeout", lambda count: 5.1
    )
    service = QualityGenerationService("volcengine", Mock(return_value="test-key"))

    async def generate(body, *args, **kwargs):
        if body.batchStart == 0:
            raise QualityGenerationError(
                "request-id: cloud-request\nFull provider error\nLAST LINE"
            )
        await asyncio.Event().wait()

    monkeypatch.setattr(service, "_generate", generate)
    with pytest.raises(QualityGenerationError) as failure:
        asyncio.run(service.generate(request(50)))
    assert "Batch 1-20" in failure.value.diagnostics
    assert "Full provider error\nLAST LINE" in failure.value.diagnostics
    assert "Batch 41-50" in failure.value.diagnostics


def test_disconnect_stops_dataset_generation(monkeypatch):
    started = asyncio.Event()
    cancelled = []

    async def generate(self, body):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.append(True)

    async def disconnected(self):
        await started.wait()
        return True

    monkeypatch.setattr(QualityGenerationService, "generate", generate)
    monkeypatch.setattr(Request, "is_disconnected", disconnected)
    app = FastAPI()
    mount_quality_routes(
        app,
        provider="volcengine",
        resolve_api_key=Mock(),
        authorize=Mock(),
        authorize_runtime=Mock(),
    )
    response = TestClient(app).post(
        "/web/quality/generate", json=request().model_dump()
    )
    assert response.status_code == 499
    assert cancelled == [True]
