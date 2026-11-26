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

import pytest

from veadk.models import ark_llm


class _FakeResponses:
    def __init__(self, response=None, error=None):
        self._response = response
        self._error = error

    async def create(self, **kwargs):
        if self._error is not None:
            raise self._error
        return self._response


class _FakeAsyncArk:
    def __init__(self, responses):
        self.responses = responses


@pytest.mark.asyncio
async def test_aresponses_logs_client_and_request_boundaries(monkeypatch):
    messages: list[str] = []
    monkeypatch.setattr(
        ark_llm.logger,
        "info",
        lambda message, *args, **kwargs: messages.append(message),
    )
    sentinel = object()
    fake_client = _FakeAsyncArk(_FakeResponses(response=sentinel))
    monkeypatch.setattr(ark_llm, "AsyncArk", lambda **kwargs: fake_client)

    result = await ark_llm.ArkLlmClient().aresponses(
        model="test-model",
        stream=True,
        input=[],
        api_key="test-key",
        api_base="http://example.com",
    )

    assert result is sentinel
    assert any("client create begin" in m and "model=test-model" in m for m in messages)
    assert any("client create end" in m for m in messages)
    assert any("responses.create begin" in m and "stream=True" in m for m in messages)
    assert any("responses.create end" in m for m in messages)


@pytest.mark.asyncio
async def test_aresponses_logs_request_error(monkeypatch):
    warnings: list[str] = []
    monkeypatch.setattr(
        ark_llm.logger,
        "warning",
        lambda message, *args, **kwargs: warnings.append(message),
    )
    fake_client = _FakeAsyncArk(_FakeResponses(error=RuntimeError("boom")))
    monkeypatch.setattr(ark_llm, "AsyncArk", lambda **kwargs: fake_client)

    with pytest.raises(RuntimeError, match="boom"):
        await ark_llm.ArkLlmClient().aresponses(
            model="test-model",
            api_key="test-key",
            api_base="http://example.com",
        )

    assert any(
        "responses.create error" in m and "error=RuntimeError" in m for m in warnings
    )


@pytest.mark.asyncio
async def test_aresponses_survives_logging_failure(monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("log backend down")

    monkeypatch.setattr(ark_llm.logger, "info", fail)
    monkeypatch.setattr(ark_llm.logger, "warning", fail)
    sentinel = object()
    fake_client = _FakeAsyncArk(_FakeResponses(response=sentinel))
    monkeypatch.setattr(ark_llm, "AsyncArk", lambda **kwargs: fake_client)

    result = await ark_llm.ArkLlmClient().aresponses(
        model="test-model",
        api_key="test-key",
        api_base="http://example.com",
    )

    assert result is sentinel


@pytest.mark.asyncio
async def test_aresponses_error_is_not_masked_by_logging_failure(monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("log backend down")

    monkeypatch.setattr(ark_llm.logger, "warning", fail)
    fake_client = _FakeAsyncArk(_FakeResponses(error=RuntimeError("boom")))
    monkeypatch.setattr(ark_llm, "AsyncArk", lambda **kwargs: fake_client)

    with pytest.raises(RuntimeError, match="boom"):
        await ark_llm.ArkLlmClient().aresponses(
            model="test-model",
            api_key="test-key",
            api_base="http://example.com",
        )
