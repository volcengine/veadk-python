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
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from frontend.server.quality.models import (
    ComponentGenerationRequest,
    ComponentPreferences,
    EvaluatorDefinition,
    PreferencesRequest,
    PreferenceSuggestions,
    PreferenceSuggestionsRequest,
    EvaluationBrief,
    EvaluationDimension,
    DatasetBatchRequest,
    GeneratedDatasetBatch,
    GeneratedDataset,
    GeneratedEvaluators,
    GenerateRequest,
    QualityRequest,
)
from frontend.server.quality.routes import mount_quality_routes
from frontend.server.quality.service import QualityGenerationService
from frontend.server.quality.errors import QualityGenerationError


@pytest.mark.parametrize(
    "method,path",
    [
        ("autofill", "autofill"),
        ("generate_evaluators", "evaluators"),
        ("suggest_preferences", "preference-suggestions"),
    ],
)
def test_routes_require_management_and_runtime_access(monkeypatch, method, path):
    generate = AsyncMock()
    monkeypatch.setattr(QualityGenerationService, method, generate)
    authorize = Mock(side_effect=HTTPException(403, "denied"))
    runtime = Mock()
    app = FastAPI()
    mount_quality_routes(
        app,
        provider="volcengine",
        resolve_api_key=Mock(),
        authorize=authorize,
        authorize_runtime=runtime,
    )
    client = TestClient(app)
    body = {"agent": {"name": "agent"}, "runtimeId": "runtime", "region": "cn-beijing"}
    if method == "suggest_preferences":
        body["field"] = "goal"
    assert client.post(f"/web/quality/{path}", json=body).status_code == 403
    runtime.assert_not_called()
    generate.assert_not_called()
    authorize.side_effect = None
    runtime.side_effect = HTTPException(404, "denied")
    assert client.post(f"/web/quality/{path}", json=body).status_code == 404
    assert runtime.call_args.args[1:] == ("runtime", "cn-beijing")
    generate.assert_not_called()


@pytest.mark.parametrize(
    "error,status,code",
    [
        (
            ValueError("model response failed api_key=private-value"),
            502,
            "quality_generation_failed",
        ),
        (TimeoutError(), 504, "quality_generation_timeout"),
        (asyncio.TimeoutError(), 504, "quality_generation_timeout"),
    ],
)
def test_provider_errors_are_safe_and_actionable(monkeypatch, error, status, code):
    monkeypatch.setattr(
        QualityGenerationService, "autofill", AsyncMock(side_effect=error)
    )
    app = FastAPI()
    mount_quality_routes(
        app,
        provider="volcengine",
        resolve_api_key=Mock(),
        authorize=Mock(),
        authorize_runtime=Mock(),
    )
    response = TestClient(app).post(
        "/web/quality/autofill", json={"agent": {"name": "agent"}}
    )
    assert response.status_code == status
    assert response.json()["detail"]["code"] == code
    assert response.json()["detail"]["diagnostics"]
    assert "private-value" not in response.text


@pytest.mark.parametrize(
    "changes",
    [
        {"count": 49},
        {"count": 301},
        {"count": 50.5},
        {"count": True},
        {"scenario": " "},
        {"requirements": "x" * 6001},
    ],
)
def test_invalid_generation_request_does_not_invoke_model(monkeypatch, changes):
    generate = AsyncMock()
    monkeypatch.setattr(QualityGenerationService, "generate", generate)
    app = FastAPI()
    mount_quality_routes(
        app,
        provider="volcengine",
        resolve_api_key=Mock(),
        authorize=Mock(),
        authorize_runtime=Mock(),
    )
    body = {
        "agent": {"name": "agent"},
        "preference": "balanced",
        "scenario": "normal use",
        "requirements": "correct answers",
        "count": 50,
        **changes,
    }
    assert TestClient(app).post("/web/quality/generate", json=body).status_code == 422
    generate.assert_not_called()


@pytest.mark.parametrize(
    "provider,host,model_name",
    [
        (
            "volcengine",
            "https://ark.cn-beijing.volces.com/api/v3",
            "doubao-seed-2-0-lite-260428",
        ),
        (
            "byteplus",
            "https://ark.ap-southeast.bytepluses.com/api/v3",
            "seed-2-0-lite-260228",
        ),
    ],
)
@pytest.mark.parametrize(
    "method,schema",
    [
        ("autofill", EvaluationBrief),
        ("suggest_preferences", PreferenceSuggestions),
        ("generate_preferences", ComponentPreferences),
        ("generate", GeneratedDataset),
        ("generate_evaluators", GeneratedEvaluators),
    ],
)
def test_quality_generation_uses_planner_model_and_output_schema(
    monkeypatch, provider, host, model_name, method, schema
):
    import json

    payload = {
        "preference": "trajectory",
        "scenario": "lookup order",
        "requirements": "verify order ID",
    }
    if method == "generate_evaluators":
        payload = evaluator_bundle()
    elif method == "suggest_preferences":
        payload = {"suggestions": suggestion_bundle()["goal"]}
    elif method == "generate_preferences":
        payload = component_preferences()
    elif method == "generate":
        payload = {
            "name": "Orders",
            "description": "Order cases",
            "items": [
                {
                    "name": f"Case {i}",
                    "scenario": "lookup",
                    "input": f"order {i}",
                    "expectedOutput": "status",
                    "trajectory": ["lookup_order"],
                    "checks": ["correct order"],
                }
                for i in range(5)
            ],
        }
    runs = []
    factory = Mock(side_effect=lambda **kwargs: SimpleNamespace(**kwargs))

    def make_runner(*, agent, app_name):
        part = payload
        if agent.output_schema is EvaluatorDefinition:
            kind = next(
                kind
                for kind in payload
                if f"Generate only the {kind} evaluator" in agent.instruction
            )
            part = payload[kind]
        if agent.output_schema is GeneratedDatasetBatch:

            async def generate_batch(raw, **kwargs):
                body = DatasetBatchRequest.model_validate_json(raw)
                return dataset_batch(body.batchStart, body.batchCount).model_dump_json()

            run = AsyncMock(side_effect=generate_batch)
        else:
            run = AsyncMock(return_value=json.dumps(part))
        runs.append(run)
        return SimpleNamespace(run=run)

    runner = Mock(side_effect=make_runner)
    monkeypatch.setattr("veadk.Agent", factory)
    monkeypatch.setattr("veadk.Runner", runner)
    resolve_api_key = Mock(return_value="test-key")
    service = QualityGenerationService(provider, resolve_api_key)
    request = QualityRequest.model_validate(
        dict(
            agent={
                "name": "orders",
                "instruction": "Check order IDs",
                "tools": ["lookup_order"],
                "skills": ["order_report"],
                "subAgents": ["shipping"],
                "toolDetails": [
                    {"name": "lookup_order", "description": "Find an order by its ID"}
                ],
                "skillDetails": [
                    {
                        "name": "order_report",
                        "description": "Report order status and ETA",
                    }
                ],
                "subAgentDetails": [
                    {
                        "name": "shipping",
                        "path": ["orders", "shipping"],
                        "instruction": "Verify the carrier's delivery estimate",
                    }
                ],
            },
            language="en-US",
        )
    )
    if method == "generate":
        request = GenerateRequest.model_validate(
            dict(
                **request.model_dump(),
                preference="trajectory",
                scenario="lookup order",
                requirements="verify order ID",
                count=50,
            )
        )
    elif method == "generate_preferences":
        request = PreferencesRequest.model_validate(
            dict(**request.model_dump(), overallPreferences=overall_preferences())
        )
    elif method == "suggest_preferences":
        request = PreferenceSuggestionsRequest.model_validate(
            dict(**request.model_dump(), field="goal")
        )
    result = asyncio.run(getattr(service, method)(request))
    assert isinstance(result, schema)
    expected_schemas = (
        [EvaluatorDefinition] * 3
        if method == "generate_evaluators"
        else [GeneratedDatasetBatch] * 3
        if method == "generate"
        else [schema]
    )
    assert [
        call.kwargs["output_schema"] for call in factory.call_args_list
    ] == expected_schemas
    resolve_api_key.assert_called_once()
    for call in factory.call_args_list:
        args = call.kwargs
        assert args["model_name"] == model_name
        assert args["model_provider"] == "openai"
        assert args["model_api_base"] == host
        assert args["model_api_key"] == "test-key"
        assert args["enable_responses"] is True
        assert args["enable_responses_cache"] is False
        assert args["model_extra_config"] == {
            "extra_body": {"thinking": {"type": "disabled"}}
        }
    for index, run in enumerate(runs):
        expected = request.model_dump(by_alias=True)
        if method == "generate":
            assert isinstance(request, GenerateRequest)
            expected.update(
                batchStart=index * 20, batchCount=min(20, request.count - index * 20)
            )
        assert json.loads(run.call_args.args[0]) == expected
        assert run.call_args.kwargs["session_id"].startswith(
            "studio_quality_generator-"
        )
    assert len({run.call_args.kwargs["session_id"] for run in runs}) == len(
        expected_schemas
    )


def dataset_batch(start, count):
    return GeneratedDatasetBatch.model_validate(
        dict(
            name="Orders",
            description="Order cases",
            items=[
                {
                    "name": f"Case {i}",
                    "scenario": "lookup",
                    "input": f"order {i}",
                    "expectedOutput": "status",
                    "trajectory": ["lookup_order"],
                    "checks": ["correct order"],
                }
                for i in range(start, start + count)
            ],
        )
    )


@pytest.mark.parametrize("invalid", ["partial", "duplicate", None])
def test_generation_rejects_partial_and_duplicate_cases(invalid):
    service = QualityGenerationService("volcengine", Mock(return_value="test-key"))

    def generate_batch(body, *args, **kwargs):
        dataset = dataset_batch(
            body.batchStart, body.batchCount - (1 if invalid == "partial" else 0)
        )
        if invalid == "duplicate":
            dataset.items[0].input = "same input"
        return dataset

    service._generate = AsyncMock(side_effect=generate_batch)
    request = GenerateRequest.model_validate(
        dict(
            agent={"name": "orders"},
            preference="trajectory",
            scenario="order lookup",
            requirements="correct ID",
            count=50,
        )
    )
    if invalid:
        with pytest.raises((ValueError, QualityGenerationError)):
            asyncio.run(service.generate(request))
    else:
        assert len(asyncio.run(service.generate(request)).items) == 50


def evaluator_bundle():
    return {
        kind: {
            "name": "Generated name",
            "description": f"Evaluate {kind}",
            "dimensions": [
                {
                    "name": "Correctness",
                    "description": "Answer correctness",
                    "basis": "0: incorrect; 3: partially correct; 5: fully supported by evidence",
                    "minScore": 0,
                    "maxScore": 5,
                    "rationale": "The Agent instruction requires checking order IDs, so correctness must include matching the requested order",
                }
            ],
            "prompt": f"Evaluate {kind} with supporting evidence",
        }
        for kind in ("overall", "tools", "skills")
    }


def overall_preferences():
    return {
        "name": "Order review",
        "goal": "Verify delivery answers",
        "scenarios": "Order lookup",
        "successCriteria": "Correct order and ETA",
        "unacceptableErrors": "Invented delivery date",
        "preference": "balanced",
    }


def component_preferences():
    return {
        "dataset": {
            "preference": "outcome",
            "scenario": "Missing order IDs",
            "requirements": "Ask for the order ID",
            "count": 50,
        },
        "evaluators": {
            "overallFocus": "Answer the requested order",
            "toolsFocus": "Check lookup_order",
            "skillsFocus": "Check order_report",
            "criteria": "Use returned ETA only",
            "strictness": "strict",
        },
    }


def suggestion_bundle():
    return {
        "goal": [
            {
                "label": "Order answers",
                "text": "Verify that answers use the correct order",
            }
        ],
        "scenarios": [
            {
                "label": "Missing order ID",
                "text": "A user asks about delivery without providing an order ID",
            }
        ],
        "successCriteria": [
            {
                "label": "Verify dates",
                "text": "Use the delivery estimate returned by lookup_order",
            }
        ],
        "unacceptableErrors": [
            {
                "label": "Invented ETA",
                "text": "Do not promise an unverified delivery date",
            }
        ],
    }


@pytest.mark.parametrize(
    "invalid", ["missing_field", "empty", "duplicate", "long_label", "multiline"]
)
def test_suggestion_contract_rejects_unusable_options(invalid):
    payload = {"suggestions": suggestion_bundle()["goal"]}
    if invalid == "missing_field":
        payload.pop("suggestions")
    elif invalid == "empty":
        payload["suggestions"] = []
    elif invalid == "duplicate":
        payload["suggestions"] *= 2
    elif invalid == "long_label":
        payload["suggestions"][0]["label"] = "x" * 19
    else:
        payload["suggestions"][0]["text"] = "First line\nSecond line"
    with pytest.raises(ValidationError):
        PreferenceSuggestions.model_validate(payload)


@pytest.mark.parametrize(
    "field", ["goal", "scenarios", "successCriteria", "unacceptableErrors"]
)
def test_suggestions_generate_only_the_requested_field(field):
    service = QualityGenerationService("volcengine", Mock())
    service._generate = AsyncMock(
        return_value=PreferenceSuggestions.model_validate(
            dict(suggestions=suggestion_bundle()[field])
        )
    )
    request = PreferenceSuggestionsRequest.model_validate(
        dict(agent={"name": "orders"}, field=field)
    )
    result = asyncio.run(service.suggest_preferences(request))
    assert result.suggestions[0].text == suggestion_bundle()[field][0]["text"]
    args = service._generate.call_args.args
    assert args[:2] == (request, PreferenceSuggestions)
    assert f"only the {field} field" in args[2]


@pytest.mark.parametrize("provider", ["volcengine", "byteplus"])
@pytest.mark.parametrize(
    "field",
    [
        "datasetScenarios",
        "datasetRequirements",
        "overallFocus",
        "toolsFocus",
        "skillsFocus",
        "criteria",
    ],
)
def test_component_suggestions_honor_overall_and_component_preferences(provider, field):
    service = QualityGenerationService(provider, Mock())
    service._generate = AsyncMock(
        return_value=PreferenceSuggestions.model_validate(
            dict(suggestions=suggestion_bundle()["goal"])
        )
    )
    request = PreferenceSuggestionsRequest.model_validate(
        dict(
            agent={
                "name": "orders",
                "instruction": "Verify the order ID before lookup",
            },
            field=field,
            overallPreferences=overall_preferences(),
            componentPreferences=component_preferences(),
        )
    )
    asyncio.run(service.suggest_preferences(request))
    args = service._generate.call_args.args
    assert args[:2] == (request, PreferenceSuggestions)
    assert f"only the {field} field" in args[2]
    assert "overallPreferences" in args[2]
    assert "componentPreferences" in args[2]
    assert "Do not repeat" in args[2]


@pytest.mark.parametrize("missing", ["overallPreferences", "componentPreferences"])
def test_component_suggestions_require_the_preference_context(missing):
    body = {
        "agent": {"name": "orders"},
        "field": "datasetScenarios",
        "overallPreferences": overall_preferences(),
        "componentPreferences": component_preferences(),
    }
    body.pop(missing)
    with pytest.raises(ValidationError):
        PreferenceSuggestionsRequest.model_validate(body)


@pytest.mark.parametrize("field", [None, "unknown"])
def test_invalid_suggestion_field_does_not_invoke_model(monkeypatch, field):
    generate = AsyncMock()
    monkeypatch.setattr(QualityGenerationService, "suggest_preferences", generate)
    app = FastAPI()
    mount_quality_routes(
        app,
        provider="volcengine",
        resolve_api_key=Mock(),
        authorize=Mock(),
        authorize_runtime=Mock(),
    )
    body = {"agent": {"name": "orders"}}
    if field is not None:
        body["field"] = field
    assert (
        TestClient(app)
        .post("/web/quality/preference-suggestions", json=body)
        .status_code
        == 422
    )
    generate.assert_not_called()


def test_preferences_require_runtime_authorization(monkeypatch):
    generate = AsyncMock()
    monkeypatch.setattr(QualityGenerationService, "generate_preferences", generate)
    app = FastAPI()
    authorize = Mock()
    runtime = Mock(side_effect=HTTPException(403, "denied"))
    mount_quality_routes(
        app,
        provider="byteplus",
        resolve_api_key=Mock(),
        authorize=authorize,
        authorize_runtime=runtime,
    )
    response = TestClient(app).post(
        "/web/quality/preferences",
        json={
            "agent": {"name": "orders"},
            "runtimeId": "runtime",
            "region": "ap-southeast-1",
            "overallPreferences": overall_preferences(),
        },
    )
    assert response.status_code == 403
    authorize.assert_called_once()
    runtime.assert_called_once()
    generate.assert_not_called()


@pytest.mark.parametrize("endpoint", ["generate", "evaluators"])
@pytest.mark.parametrize("count", [50, 77, 300])
def test_generation_receives_reviewed_preferences(monkeypatch, endpoint, count):
    bundle = component_preferences()
    bundle["dataset"]["count"] = count
    bundle["evaluators"]["criteria"] = (
        "User edited: refuse unverified delivery promises"
    )
    generate = AsyncMock(
        side_effect=lambda body, *args, **kwargs: (
            EvaluatorDefinition.model_validate(evaluator_bundle()["overall"])
            if endpoint == "evaluators"
            else dataset_batch(body.batchStart, body.batchCount)
        )
    )
    monkeypatch.setattr(QualityGenerationService, "_generate", generate)
    app = FastAPI()
    mount_quality_routes(
        app,
        provider="volcengine",
        resolve_api_key=Mock(),
        authorize=Mock(),
        authorize_runtime=Mock(),
    )
    body = {
        "agent": {"name": "orders", "instruction": "Verify order IDs"},
        "overallPreferences": overall_preferences(),
        "componentPreferences": bundle,
    }
    if endpoint == "generate":
        body.update(bundle["dataset"])
    response = TestClient(app).post(f"/web/quality/{endpoint}", json=body)
    assert response.status_code == 200
    if endpoint == "generate":
        assert len(response.json()["items"]) == count
    sent = generate.call_args.args[0].model_dump()
    assert sent["overallPreferences"] == overall_preferences()
    assert sent["componentPreferences"] == bundle


def test_dataset_request_rejects_unreviewed_overrides():
    with pytest.raises(ValidationError, match="reviewed dataset preferences"):
        GenerateRequest.model_validate(
            dict(
                agent={"name": "orders"},
                componentPreferences=component_preferences(),
                **{**component_preferences()["dataset"], "count": 100},
            )
        )


@pytest.mark.parametrize(
    "language,names",
    [
        ("zh-CN", ["综合评估器", "工具能力评估器", "Skill 评估器"]),
        (
            "en-US",
            ["Overall evaluator", "Tool capability evaluator", "Skill evaluator"],
        ),
    ],
)
def test_evaluators_always_include_all_three_categories(monkeypatch, language, names):
    generated = EvaluatorDefinition.model_validate(evaluator_bundle()["overall"])
    model = AsyncMock(
        side_effect=lambda *args, **kwargs: generated.model_copy(deep=True)
    )
    monkeypatch.setattr(QualityGenerationService, "_generate", model)
    app = FastAPI()
    mount_quality_routes(
        app,
        provider="byteplus",
        resolve_api_key=Mock(),
        authorize=Mock(),
        authorize_runtime=Mock(),
    )
    response = TestClient(app).post(
        "/web/quality/evaluators",
        json={
            "agent": {"name": "Assistant", "instruction": "Answer clearly"},
            "language": language,
        },
    )
    assert response.status_code == 200
    assert list(response.json()) == ["overall", "tools", "skills"]
    assert [value["name"] for value in response.json().values()] == names
    assert model.call_args.args[0].agent.instruction == "Answer clearly"
    assert all(
        value["prompt"] and value["dimensions"] for value in response.json().values()
    )


@pytest.mark.parametrize("invalid", ["missing", "extra", "blank_prompt"])
def test_evaluator_schema_rejects_incomplete_or_unexpected_definitions(invalid):
    bundle = evaluator_bundle()
    if invalid == "missing":
        bundle.pop("skills")
    elif invalid == "extra":
        bundle["other"] = bundle["overall"]
    else:
        bundle["skills"]["prompt"] = " "
    with pytest.raises(ValidationError):
        GeneratedEvaluators.model_validate(bundle)


@pytest.mark.parametrize(
    "changes",
    [
        {"name": " "},
        {"description": " "},
        {"basis": " "},
        {"rationale": " "},
        {"rationale": "x" * 1601},
        {"minScore": 5, "maxScore": 5},
        {"minScore": 6, "maxScore": 5},
        {"minScore": float("nan")},
        {"maxScore": float("inf")},
        {"minScore": "0"},
        {"maxScore": True},
    ],
)
def test_dimension_rejects_empty_fields_and_invalid_score_bounds(changes):
    dimension = evaluator_bundle()["overall"]["dimensions"][0]
    with pytest.raises(ValidationError):
        EvaluationDimension.model_validate({**dimension, **changes})


@pytest.mark.parametrize(
    "field", ["name", "description", "basis", "minScore", "maxScore", "rationale"]
)
def test_all_dimension_fields_are_required(field):
    dimension = evaluator_bundle()["overall"]["dimensions"][0]
    dimension.pop(field)
    with pytest.raises(ValidationError):
        EvaluationDimension.model_validate(dimension)


def test_evaluators_start_together_and_preserve_category_mapping(monkeypatch):
    async def scenario():
        started = set()
        all_started = asyncio.Event()
        release = {kind: asyncio.Event() for kind in evaluator_bundle()}
        completed = []

        async def generate(request, schema, task, **kwargs):
            kind = task.split()[3]
            started.add(kind)
            if len(started) == 3:
                all_started.set()
            await release[kind].wait()
            completed.append(kind)
            return EvaluatorDefinition.model_validate(evaluator_bundle()[kind])

        service = QualityGenerationService("volcengine", lambda: "test-key")
        monkeypatch.setattr(service, "_generate", generate)
        operation = asyncio.create_task(
            service.generate_evaluators(
                ComponentGenerationRequest.model_validate(
                    dict(agent={"name": "orders"})
                )
            )
        )
        try:
            await asyncio.wait_for(all_started.wait(), 1)
            for kind in ("skills", "tools", "overall"):
                release[kind].set()
            result = await operation
            assert completed == ["skills", "tools", "overall"]
            assert result.overall.description == "Evaluate overall"
            assert result.tools.description == "Evaluate tools"
            assert result.skills.description == "Evaluate skills"
        finally:
            operation.cancel()
            await asyncio.gather(operation, return_exceptions=True)

    asyncio.run(scenario())


def test_cancelling_evaluator_generation_cancels_every_model_call(monkeypatch):
    async def scenario():
        started = set()
        stopped = set()
        all_started = asyncio.Event()

        async def generate(request, schema, task, **kwargs):
            kind = task.split()[3]
            started.add(kind)
            if len(started) == 3:
                all_started.set()
            try:
                await asyncio.Event().wait()
            finally:
                stopped.add(kind)

        service = QualityGenerationService("byteplus", lambda: "test-key")
        monkeypatch.setattr(service, "_generate", generate)
        operation = asyncio.create_task(
            service.generate_evaluators(
                ComponentGenerationRequest.model_validate(
                    dict(agent={"name": "orders"})
                )
            )
        )
        try:
            await asyncio.wait_for(all_started.wait(), 1)
        finally:
            operation.cancel()
            with pytest.raises(asyncio.CancelledError):
                await operation
        assert stopped == {"overall", "tools", "skills"}

    asyncio.run(scenario())


def test_parallel_timeout_preserves_errors_from_completed_model_calls(monkeypatch):
    monkeypatch.setattr(
        "frontend.server.quality.service.PARALLEL_GENERATION_TIMEOUT_SECONDS", 0.05
    )
    diagnostic = "cloud error line\n" * 1000 + "LAST CLOUD ERROR"

    async def generate(request, schema, task, **kwargs):
        kind = task.split()[3]
        if kind != "skills":
            raise QualityGenerationError(f"{kind}: {diagnostic}")
        await asyncio.Event().wait()

    service = QualityGenerationService("volcengine", lambda: "test-key")
    monkeypatch.setattr(service, "_generate", generate)
    with pytest.raises(QualityGenerationError) as caught:
        asyncio.run(
            service.generate_evaluators(
                ComponentGenerationRequest.model_validate(
                    dict(agent={"name": "orders"})
                )
            )
        )
    assert caught.value.diagnostics.count(diagnostic) == 2
    assert "skills" in caught.value.diagnostics
    assert "deadline" in caught.value.diagnostics
    assert caught.value.timeout is False
