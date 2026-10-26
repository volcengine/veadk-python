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
from google.adk.models import LlmRequest

from veadk.consts import DEFAULT_MODEL_EXTRA_CONFIG
from veadk.models import ark_llm
from veadk.models.ark_llm import ArkLlm, ArkLlmClient


def _request(extra_body=None):
    request = {"model": "openai/test-model", "input": []}
    if extra_body is not None:
        request["extra_body"] = extra_body
    return request


def test_no_default_shortens_conversation_retention():
    """Merged origin/main policy: no injected expire_at, Ark's default applies."""
    assert "expire_at" not in DEFAULT_MODEL_EXTRA_CONFIG["extra_body"]

    request = ark_llm.request_reorganization_by_ark(_request())

    assert "expire_at" not in request["extra_body"]


def test_explicit_expire_at_has_priority_over_server_default():
    request = ark_llm.request_reorganization_by_ark(
        _request({"expire_at": 9_999_999, "custom_option": "kept"})
    )

    assert request["extra_body"] == {
        "expire_at": 9_999_999,
        "custom_option": "kept",
    }


async def _consume(model):
    return [response async for response in model.generate_content_async(LlmRequest())]


@pytest.mark.asyncio
async def test_same_model_instance_keeps_explicit_expire_at(monkeypatch):
    requests = []

    class FakeClient(ArkLlmClient):
        async def aresponses(self, **kwargs):
            requests.append(kwargs)
            return object()

    monkeypatch.setattr(
        ark_llm, "ark_response_to_generate_content_response", lambda _: None
    )

    explicit_model = ArkLlm(
        model="openai/test-model",
        llm_client=FakeClient(),
        extra_body={"expire_at": 9_999_999},
    )
    await _consume(explicit_model)

    default_model = ArkLlm(model="openai/test-model", llm_client=FakeClient())
    await _consume(default_model)

    assert requests[0]["extra_body"]["expire_at"] == 9_999_999
    assert "expire_at" not in requests[1]["extra_body"]
