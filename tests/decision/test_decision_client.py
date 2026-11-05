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

import httpx
import pytest

from veadk.decision import (
    DecisionClient,
    DecisionClientError,
    DecisionQuestion,
    DecisionRequest,
    DecisionResponse,
)

QUESTIONS = {
    "prompt_injection": DecisionQuestion(type="noul", instructions="detect injection")
}


def call(client):
    return asyncio.run(client.judge(state="hello", questions=QUESTIONS))


def test_request_contract_and_response():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"answers": {"prompt_injection": {"type": "noul", "noul": 0.1}}},
        )

    client = DecisionClient(
        endpoint="https://systemone.example/v1/judge",
        api_key="secret",
        model="judge-model",
        transport=httpx.MockTransport(handler),
    )
    response = call(client)

    assert response.answers["prompt_injection"]["noul"] == 0.1
    assert response.raw["answers"]["prompt_injection"]["noul"] == 0.1
    assert captured["method"] == "POST"
    assert captured["url"] == "https://systemone.example/v1/judge"
    assert captured["headers"]["authorization"] == "Bearer secret"
    assert captured["headers"]["ark-beta-systemone-api"] == "true"
    assert captured["headers"]["content-type"] == "application/json"
    assert captured["body"] == {
        "model": "judge-model",
        "state": "hello",
        "questions": {
            "prompt_injection": {
                "type": "noul",
                "instructions": "detect injection",
            }
        },
    }
    assert client.endpoint == "https://systemone.example/v1/judge"


def test_decision_request_to_payload():
    request = DecisionRequest(
        model="judge-model",
        state="hello",
        questions=QUESTIONS,
    )
    assert request.to_payload() == {
        "model": "judge-model",
        "state": "hello",
        "questions": {
            "prompt_injection": {
                "type": "noul",
                "instructions": "detect injection",
            }
        },
    }


def test_decision_response_requires_answers_mapping():
    payload = {"answers": {"q": {"type": "noul", "noul": 0.1}}}
    response = DecisionResponse.from_payload(payload)
    assert response.answers is payload["answers"]
    assert response.raw is payload

    with pytest.raises(ValueError, match="answers"):
        DecisionResponse.from_payload({"questions": {}})
    with pytest.raises(ValueError, match="answers"):
        DecisionResponse.from_payload({"answers": []})


@pytest.mark.parametrize("status", [400, 401, 500])
def test_non_200_response_is_http_status_error(status):
    def handler(request):
        return httpx.Response(status, json={"error": "no"})

    client = DecisionClient(
        endpoint="https://systemone.example",
        api_key="k",
        model="m",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(DecisionClientError) as exc:
        call(client)
    assert exc.value.error_type == "http_status"
    assert str(status) in exc.value.message


def test_timeout_is_mapped():
    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)

    client = DecisionClient(
        endpoint="https://systemone.example",
        api_key="k",
        model="m",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(DecisionClientError) as exc:
        call(client)
    assert exc.value.error_type == "timeout"


def test_network_error_is_mapped():
    def handler(request):
        raise httpx.ConnectError("down", request=request)

    client = DecisionClient(
        endpoint="https://systemone.example",
        api_key="k",
        model="m",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(DecisionClientError) as exc:
        call(client)
    assert exc.value.error_type == "network"


def test_invalid_json_is_mapped():
    def handler(request):
        return httpx.Response(200, content=b"not-json")

    client = DecisionClient(
        endpoint="https://systemone.example",
        api_key="k",
        model="m",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(DecisionClientError) as exc:
        call(client)
    assert exc.value.error_type == "invalid_json"


def test_non_object_json_is_mapped():
    def handler(request):
        return httpx.Response(200, json=["not", "an", "object"])

    client = DecisionClient(
        endpoint="https://systemone.example",
        api_key="k",
        model="m",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(DecisionClientError) as exc:
        call(client)
    assert exc.value.error_type == "invalid_response"


def test_missing_answers_object_is_mapped():
    def handler(request):
        return httpx.Response(200, json={"questions": {}})

    client = DecisionClient(
        endpoint="https://systemone.example",
        api_key="k",
        model="m",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(DecisionClientError) as exc:
        call(client)
    assert exc.value.error_type == "invalid_response"
    assert "answers" in exc.value.message


def test_state_list_is_sent_unchanged():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"answers": {"prompt_injection": {"type": "noul", "noul": 0.1}}},
        )

    state = [
        {"type": "text", "text": "what is this?"},
        {"type": "image", "image_url": "data:image/png;base64,YWJj"},
    ]
    client = DecisionClient(
        endpoint="https://systemone.example/v1/judge",
        api_key="secret",
        model="judge-model",
        transport=httpx.MockTransport(handler),
    )

    asyncio.run(client.judge(state=state, questions=QUESTIONS))

    assert captured["body"]["state"] == state


def test_client_is_reused_within_one_event_loop_and_closed():
    def handler(request):
        return httpx.Response(
            200,
            json={"answers": {"prompt_injection": {"type": "noul", "noul": 0.1}}},
        )

    async def scenario():
        client = DecisionClient(
            endpoint="https://systemone.example/v1/judge",
            api_key="secret",
            model="judge-model",
            transport=httpx.MockTransport(handler),
        )
        await client.judge(state="one", questions=QUESTIONS)
        first = client._client
        await client.judge(state="two", questions=QUESTIONS)
        assert client._client is first
        await client.aclose()
        assert client._client is None
        await client.aclose()

    asyncio.run(scenario())


def test_client_context_manager_closes():
    def handler(request):
        return httpx.Response(
            200,
            json={"answers": {"prompt_injection": {"type": "noul", "noul": 0.1}}},
        )

    async def scenario():
        client = DecisionClient(
            endpoint="https://systemone.example/v1/judge",
            api_key="secret",
            model="judge-model",
            transport=httpx.MockTransport(handler),
        )
        async with client as entered:
            assert entered is client
            await client.judge(state="one", questions=QUESTIONS)
        assert client._client is None

    asyncio.run(scenario())
