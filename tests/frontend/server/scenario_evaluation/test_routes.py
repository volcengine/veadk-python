from __future__ import annotations

from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from frontend.server.scenario_evaluation.executor import (
    FormalEvaluationExecutor,
    RuntimeEvidence,
    RuntimeHandle,
)
from frontend.server.scenario_evaluation.evaluators import ControlledEvidenceEvaluator
from frontend.server.scenario_evaluation.models import (
    AttemptOutcome,
    EvaluatorEvidence,
    ScenarioActor,
)
from frontend.server.scenario_evaluation.publishing import PublishCandidateService
from frontend.server.scenario_evaluation.repository import (
    InMemoryScenarioEvaluationRepository,
)
from frontend.server.scenario_evaluation.routes import mount_routes
from frontend.server.scenario_evaluation.run_service import FormalEvaluationManager
from frontend.server.scenario_evaluation.service import ScenarioEvaluationService
from veadk.cli.studio_rbac import StudioRole


class _Ids:
    def __init__(self) -> None:
        self.value = 0

    def __call__(self, prefix: str) -> str:
        self.value += 1
        return f"{prefix}-{self.value}"


class _UnusedRuntime:
    async def create(self, candidate):  # type: ignore[no-untyped-def]
        return RuntimeHandle("runtime", candidate.candidate_id)

    async def run_case(self, handle, case, **kwargs):  # type: ignore[no-untyped-def]
        del handle, case, kwargs
        return RuntimeEvidence(output="ok", trace_ref="trace")

    async def close(self, handle):  # type: ignore[no-untyped-def]
        del handle


class _PassEvaluator:
    async def evaluate(self, evaluator, case, evidence, **kwargs):  # type: ignore[no-untyped-def]
        del case, evidence, kwargs
        return EvaluatorEvidence(
            evaluator_version_id=evaluator.evaluator_version_id,
            outcome=AttemptOutcome.PASS,
        )


def _app() -> FastAPI:
    repository = InMemoryScenarioEvaluationRepository()
    ids = _Ids()

    def clock() -> datetime:
        return datetime(2026, 8, 14, 12, tzinfo=timezone.utc)

    async def trust_agent_identity(*_args: object) -> None:
        return None

    service = ScenarioEvaluationService(
        repository,
        clock=clock,
        id_factory=ids,
        project_attestation_verifier=lambda _project, _owner, _proof: None,
        agent_identity_verifier=trust_agent_identity,
    )
    manager = FormalEvaluationManager(
        repository,
        service,
        FormalEvaluationExecutor(_UnusedRuntime(), _PassEvaluator()),
        clock=clock,
        id_factory=ids,
    )
    publisher = PublishCandidateService(
        repository,
        service,
        clock=clock,
        id_factory=ids,
    )

    def actor(request: Request) -> ScenarioActor:
        owner = request.headers.get("X-Test-User", "user-1")
        role = StudioRole(request.headers.get("X-Test-Role", "user"))
        return ScenarioActor(
            owner_id=owner,
            display_name=owner,
            role=role,
            identifiers=(owner,),
        )

    app = FastAPI()
    mount_routes(
        app,
        service=service,
        run_manager=manager,
        publisher=publisher,
        actor_resolver=actor,
        evidence_evaluator=ControlledEvidenceEvaluator(),
    )
    return app


def _candidate_payload() -> dict[str, object]:
    return {
        "agentId": "agent-1",
        "artifact": {
            "codeDigest": "sha256:code",
            "topologyDigest": "sha256:topology",
            "environmentRefs": [
                {"name": "MODEL_API_KEY", "reference": "secret://model-key"}
            ],
        },
    }


def test_candidate_route_enforces_role_and_returns_camel_case() -> None:
    with TestClient(_app()) as client:
        forbidden = client.post(
            "/web/scenario-evaluation/candidates",
            headers={"X-Test-Role": "user"},
            json=_candidate_payload(),
        )
        created = client.post(
            "/web/scenario-evaluation/candidates",
            headers={"X-Test-Role": "developer", "X-Test-User": "developer-1"},
            json=_candidate_payload(),
        )

    assert forbidden.status_code == 403
    assert forbidden.json()["detail"]["code"] == "forbidden"
    assert created.status_code == 200
    assert created.json()["candidateId"].startswith("candidate-")
    assert "candidate_id" not in created.json()


def test_evaluator_recommendation_and_trial_routes_return_persisted_evidence() -> None:
    with TestClient(_app()) as client:
        draft = client.post(
            "/web/scenario-evaluation/scene-drafts",
            headers={"X-Test-Role": "developer"},
            json={
                "agentId": "agent-1",
                "sceneId": "scene-1",
                "expectedRevision": 0,
                "name": "事实查询",
                "description": "回答必须包含已发货",
                "userTask": "查询订单物流状态",
                "passCriteria": ["回答包含真实物流状态"],
                "hardFailureConditions": ["不得编造物流状态"],
                "ownerId": "order-owner",
                "requirement": "must_pass",
            },
        ).json()
        scene = client.post(
            "/web/scenario-evaluation/scene-versions/publish",
            headers={"X-Test-Role": "admin"},
            json={
                "agentId": "agent-1",
                "assetId": "scene-1",
                "draftRevision": draft["revision"],
            },
        ).json()
        invalid_regex = client.post(
            "/web/scenario-evaluation/evaluator-drafts",
            headers={"X-Test-Role": "developer"},
            json={
                "agentId": "agent-1",
                "evaluatorId": "invalid-regex",
                "expectedRevision": 0,
                "name": "无效正则检查",
                "sceneVersionId": scene["sceneVersionId"],
                "kind": "deterministic",
                "rule": "output_matches_regex",
                "regexPattern": "[unclosed",
                "hardFailure": False,
            },
        )
        dataset_draft = client.post(
            "/web/scenario-evaluation/dataset-drafts",
            headers={"X-Test-Role": "developer"},
            json={
                "agentId": "agent-1",
                "datasetId": "dataset-1",
                "expectedRevision": 0,
                "name": "事实查询样本",
                "cases": [
                    {
                        "caseId": "case-1",
                        "sceneVersionId": scene["sceneVersionId"],
                        "input": "订单状态",
                        "expectedOutput": "已发货",
                        "passCriteria": ["回答包含真实物流状态"],
                        "forbiddenOutput": ["编造"],
                        "sourceRefs": ["manual:case-1"],
                    }
                ],
            },
        ).json()
        dataset = client.post(
            "/web/scenario-evaluation/dataset-versions/publish",
            headers={"X-Test-Role": "admin"},
            json={
                "agentId": "agent-1",
                "assetId": "dataset-1",
                "draftRevision": dataset_draft["revision"],
            },
        ).json()
        recommended = client.post(
            "/web/scenario-evaluation/evaluator-drafts/recommend",
            headers={"X-Test-Role": "developer"},
            json={
                "agentId": "agent-1",
                "sceneVersionId": scene["sceneVersionId"],
            },
        )
        deterministic = next(
            item
            for item in recommended.json()["drafts"]
            if item["kind"] == "deterministic"
        )
        trial = client.post(
            f"/web/scenario-evaluation/evaluator-drafts/{deterministic['evaluatorId']}/trial",
            headers={"X-Test-Role": "developer"},
            json={
                "agentId": "agent-1",
                "expectedRevision": deterministic["revision"],
                "datasetVersionId": dataset["datasetVersionId"],
                "samples": [
                    {
                        "sampleId": "case-1",
                        "input": "订单状态",
                        "expectedOutput": "已发货",
                        "agentOutput": "订单已发货",
                        "expectedOutcome": "pass",
                        "forbiddenOutput": ["编造"],
                    }
                ],
            },
        )

    assert recommended.status_code == 200
    assert invalid_regex.status_code == 422
    assert len(recommended.json()["drafts"]) == 2
    assert trial.status_code == 200
    assert trial.json()["results"][0]["outcome"] == "pass"


def test_evaluator_group_publish_route_rejects_duplicate_checks() -> None:
    with TestClient(_app()) as client:
        response = client.post(
            "/web/scenario-evaluation/evaluator-groups/publish",
            headers={"X-Test-Role": "admin"},
            json={
                "agentId": "agent-1",
                "sceneVersionId": "scene-1:v1",
                "drafts": [
                    {"evaluatorId": "check-1", "draftRevision": 1},
                    {"evaluatorId": "check-1", "draftRevision": 1},
                ],
            },
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "Duplicate evaluator id."


def test_workspace_reads_persisted_candidate_instead_of_demo_data() -> None:
    with TestClient(_app()) as client:
        created = client.post(
            "/web/scenario-evaluation/candidates",
            headers={"X-Test-Role": "developer", "X-Test-User": "developer-1"},
            json=_candidate_payload(),
        ).json()
        workspace = client.get(
            "/web/scenario-evaluation/workspace?agentId=agent-1",
            headers={"X-Test-Role": "developer", "X-Test-User": "developer-1"},
        )

    assert workspace.status_code == 200
    assert workspace.json()["candidates"][0]["candidateId"] == created["candidateId"]
    assert workspace.json()["runs"] == []
    assert workspace.json()["badcases"] == []


def test_candidate_route_persists_runtime_project_without_echoing_source_code() -> None:
    payload = _candidate_payload()
    payload["runtimeProject"] = {
        "name": "demo_agent",
        "files": [
            {
                "path": "agents/demo_agent/agent.py",
                "content": "root_agent = object()\n",
            }
        ],
        "deploymentProfile": {"region": "cn-beijing"},
        "attestation": "trusted-test-project",
    }

    with TestClient(_app()) as client:
        created = client.post(
            "/web/scenario-evaluation/candidates",
            headers={"X-Test-Role": "developer", "X-Test-User": "developer-1"},
            json=payload,
        )
        workspace = client.get(
            "/web/scenario-evaluation/workspace?agentId=agent-1",
            headers={"X-Test-Role": "developer", "X-Test-User": "developer-1"},
        )

    assert created.status_code == 200
    candidate = created.json()
    assert candidate["artifact"]["runtimeProjectRef"].endswith(":runtime-project")
    assert "runtimeProject" not in candidate
    assert "root_agent" not in created.text
    assert "root_agent" not in workspace.text


def test_unevaluated_publish_route_requires_confirmation_and_reason() -> None:
    with TestClient(_app()) as client:
        candidate = client.post(
            "/web/scenario-evaluation/candidates",
            headers={"X-Test-Role": "developer", "X-Test-User": "developer-1"},
            json=_candidate_payload(),
        ).json()
        invalid = client.post(
            "/web/scenario-evaluation/publish-intents/prepare",
            headers={"X-Test-Role": "developer", "X-Test-User": "developer-1"},
            json={
                "agentId": "agent-1",
                "candidateId": candidate["candidateId"],
                "policyVersionId": None,
                "environmentFingerprint": "sha256:runtime",
                "permissionFingerprint": "permission:v1",
                "secondConfirmation": False,
                "reason": "",
                "idempotencyKey": "prepare-1",
            },
        )
        prepared = client.post(
            "/web/scenario-evaluation/publish-intents/prepare",
            headers={"X-Test-Role": "developer", "X-Test-User": "developer-1"},
            json={
                "agentId": "agent-1",
                "candidateId": candidate["candidateId"],
                "policyVersionId": None,
                "environmentFingerprint": "sha256:runtime",
                "permissionFingerprint": "permission:v1",
                "secondConfirmation": True,
                "reason": "紧急修复，暂未评测",
                "idempotencyKey": "prepare-2",
            },
        )

    assert invalid.status_code == 422
    assert invalid.json()["detail"]["code"] == "invalid_transition"
    assert prepared.status_code == 200
    assert prepared.json()["path"] == "skip"
    assert prepared.json()["status"] == "prepared"


def test_publish_rejects_environment_outside_frozen_candidate_profile() -> None:
    payload = _candidate_payload()
    payload["runtimeProject"] = {
        "name": "demo_agent",
        "files": [
            {
                "path": "agents/demo_agent/agent.py",
                "content": "root_agent = object()\n",
            }
        ],
        "deploymentProfile": {"region": "cn-beijing"},
        "attestation": "trusted-test-project",
    }

    with TestClient(_app()) as client:
        candidate = client.post(
            "/web/scenario-evaluation/candidates",
            headers={"X-Test-Role": "developer", "X-Test-User": "developer-1"},
            json=payload,
        ).json()
        response = client.post(
            "/web/scenario-evaluation/publish-intents/prepare",
            headers={"X-Test-Role": "developer", "X-Test-User": "developer-1"},
            json={
                "agentId": "agent-1",
                "candidateId": candidate["candidateId"],
                "policyVersionId": None,
                "environmentFingerprint": "sha256:different-environment",
                "secondConfirmation": True,
                "reason": "紧急发布",
                "idempotencyKey": "prepare-environment-mismatch",
            },
        )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_transition"
    assert "frozen Candidate" in response.json()["detail"]["message"]


def test_removed_publish_state_mutation_routes_are_not_public() -> None:
    with TestClient(_app()) as client:
        started = client.post(
            "/web/scenario-evaluation/publish-intents/intent-1/start",
            json={"agentId": "agent-1"},
        )
        succeeded = client.post(
            "/web/scenario-evaluation/publish-intents/intent-1/succeeded",
            json={"agentId": "agent-1", "deploymentRef": "forged"},
        )

    assert started.status_code == 404
    assert succeeded.status_code == 404


def test_cancel_route_accepts_agent_request_model() -> None:
    with TestClient(_app()) as client:
        response = client.post(
            "/web/scenario-evaluation/runs/missing-run/cancel",
            headers={"X-Test-Role": "developer"},
            json={"agentId": "agent-1"},
        )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "not_found"
