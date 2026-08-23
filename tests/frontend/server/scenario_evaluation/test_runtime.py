from __future__ import annotations

from datetime import datetime, timezone

import pytest

from frontend.server.scenario_evaluation.executor import (
    EvaluationInfrastructureError,
)
from frontend.server.scenario_evaluation.models import (
    CandidateArtifact,
    CandidateProjectFile,
    CandidateProjectSnapshot,
    CandidateVersion,
    CredentialReference,
    DatasetCase,
)
from frontend.server.scenario_evaluation.runtime import (
    AllowlistedCredentialReferenceResolver,
    CandidateRuntimeMaterialization,
    GeneratedAgentEvaluationRuntime,
    ServiceCandidateRuntimeMaterializer,
)
from veadk.cli.generated_agent_codegen import GeneratedFile, GeneratedProject
from veadk.cli.generated_agent_runtime import (
    GeneratedAgentRunEvidence,
    GeneratedAgentRuntimeError,
    GeneratedAgentRuntimeHandle,
)


def _candidate() -> CandidateVersion:
    return CandidateVersion(
        candidate_id="candidate-1",
        agent_id="agent-1",
        version=1,
        artifact=CandidateArtifact(
            code_digest="sha256:code",
            topology_digest="sha256:topology",
        ),
        created_at=datetime(2026, 8, 15, tzinfo=timezone.utc),
        created_by="developer-1",
    )


class _Materializer:
    async def materialize(
        self,
        candidate: CandidateVersion,
    ) -> CandidateRuntimeMaterialization:
        assert candidate.candidate_id == "candidate-1"
        return CandidateRuntimeMaterialization(
            project=GeneratedProject(
                name="demo_agent",
                files=[
                    GeneratedFile(
                        path="agents/demo_agent/agent.py",
                        content="root_agent = object()\n",
                    )
                ],
            ),
            environment={"RESOLVED_SECRET": "ephemeral-value"},
        )


class _Manager:
    def __init__(self) -> None:
        self.created_environment: dict[str, str] | None = None
        self.closed = False
        self.fail_run = False

    async def create(self, project, *, environment, owner_id):  # type: ignore[no-untyped-def]
        assert project.name == "demo_agent"
        assert owner_id == "developer-1"
        self.created_environment = dict(environment)
        return GeneratedAgentRuntimeHandle(
            runtime_id="runtime-1",
            app_name="demo_agent",
            expires_at=100.0,
        )

    async def create_session(
        self,
        handle: GeneratedAgentRuntimeHandle,
        *,
        user_id: str,
    ) -> str:
        assert handle.runtime_id == "runtime-1"
        assert user_id == "scenario-evaluation"
        return "runtime-session-1"

    async def run_case(
        self,
        handle: GeneratedAgentRuntimeHandle,
        *,
        user_id: str,
        session_id: str,
        prompt: str,
    ) -> GeneratedAgentRunEvidence:
        if self.fail_run:
            raise GeneratedAgentRuntimeError(502, "runtime unavailable")
        assert handle.runtime_id == "runtime-1"
        assert user_id == "scenario-evaluation"
        assert session_id == "runtime-session-1"
        assert prompt == "where is my order?"
        return GeneratedAgentRunEvidence(
            output="your order is in transit",
            trace_ref="generated-agent-runtime://runtime-1/trace/runtime-session-1",
            trace=({"trace_id": "trace-1", "span_id": "span-1"},),
        )

    async def close(self, handle: GeneratedAgentRuntimeHandle) -> None:
        assert handle.runtime_id == "runtime-1"
        self.closed = True


class _ProjectService:
    async def get_candidate_runtime_project(
        self,
        *,
        agent_id: str,
        project_snapshot_id: str,
    ) -> CandidateProjectSnapshot:
        assert agent_id == "agent-1"
        assert project_snapshot_id == "candidate-1:runtime-project"
        return CandidateProjectSnapshot(
            project_snapshot_id=project_snapshot_id,
            candidate_id="candidate-1",
            agent_id=agent_id,
            name="demo_agent",
            files=(
                CandidateProjectFile(
                    path="agents/demo_agent/agent.py",
                    content="root_agent = object()\n",
                ),
            ),
            created_at=datetime(2026, 8, 15, tzinfo=timezone.utc),
            created_by="developer-1",
        )


class _CredentialResolver:
    async def resolve(self, reference: str) -> str:
        assert reference == "secret://model-key"
        return "resolved-model-key"


@pytest.mark.asyncio
async def test_allowlisted_credential_resolver_supports_env_and_ark_key_ids() -> None:
    requested_key_ids: list[str] = []
    resolver = AllowlistedCredentialReferenceResolver(
        environment=lambda: {"MODEL_AGENT_API_KEY": "env-model-key"},
        ark_api_key_resolver=lambda key_id: (
            requested_key_ids.append(key_id) or "resolved-ark-key"
        ),
    )

    assert await resolver.resolve("env://MODEL_AGENT_API_KEY") == "env-model-key"
    assert await resolver.resolve("ark-api-key://key-123") == "resolved-ark-key"
    assert requested_key_ids == ["key-123"]


@pytest.mark.asyncio
async def test_allowlisted_credential_resolver_rejects_unknown_or_missing_refs() -> (
    None
):
    resolver = AllowlistedCredentialReferenceResolver(
        environment=lambda: {},
        ark_api_key_resolver=lambda key_id: f"unused-{key_id}",
    )

    with pytest.raises(EvaluationInfrastructureError, match="not supported"):
        await resolver.resolve("secret://raw-model-key")
    with pytest.raises(EvaluationInfrastructureError, match="unavailable"):
        await resolver.resolve("env://MISSING_KEY")


@pytest.mark.asyncio
async def test_materializer_loads_server_snapshot_and_resolves_secrets_at_execution() -> (
    None
):
    candidate = _candidate().model_copy(
        update={
            "artifact": _candidate().artifact.model_copy(
                update={
                    "runtime_project_ref": "candidate-1:runtime-project",
                    "environment_refs": (
                        CredentialReference(
                            name="MODEL_AGENT_API_KEY",
                            reference="secret://model-key",
                        ),
                    ),
                }
            )
        }
    )
    materializer = ServiceCandidateRuntimeMaterializer(
        _ProjectService(),
        _CredentialResolver(),
        base_environment=lambda: {"SAFE_BASE": "enabled"},
    )

    materialized = await materializer.materialize(candidate)

    assert materialized.project.name == "demo_agent"
    assert materialized.project.files[0].path == "agents/demo_agent/agent.py"
    assert materialized.environment == {
        "SAFE_BASE": "enabled",
        "MODEL_AGENT_API_KEY": "resolved-model-key",
    }
    assert "resolved-model-key" not in candidate.model_dump_json()


@pytest.mark.asyncio
async def test_adapter_creates_runtime_session_and_returns_persistable_evidence() -> (
    None
):
    manager = _Manager()
    runtime = GeneratedAgentEvaluationRuntime(manager, _Materializer())

    handle = await runtime.create(_candidate())
    evidence = await runtime.run_case(
        handle,
        DatasetCase(
            case_id="case-1",
            input="where is my order?",
            expected_output="answer with delivery status",
            pass_criteria=("include the current delivery status",),
            forbidden_output=("claim the order was delivered without evidence",),
        ),
        session_id="session-1",
        attempt_index=1,
    )
    await runtime.close(handle)

    assert handle.candidate_id == "candidate-1"
    assert manager.created_environment == {"RESOLVED_SECRET": "ephemeral-value"}
    assert evidence.output == "your order is in transit"
    assert evidence.session_id == "runtime-session-1"
    assert evidence.trace_ref.endswith("/trace/runtime-session-1")
    assert evidence.trace_json == ('[{"trace_id":"trace-1","span_id":"span-1"}]')
    assert "ephemeral-value" not in evidence.trace_json
    assert manager.closed is True


@pytest.mark.asyncio
async def test_adapter_maps_runtime_failure_to_retryable_infrastructure_error() -> None:
    manager = _Manager()
    manager.fail_run = True
    runtime = GeneratedAgentEvaluationRuntime(manager, _Materializer())
    handle = await runtime.create(_candidate())

    with pytest.raises(EvaluationInfrastructureError, match="runtime unavailable"):
        await runtime.run_case(
            handle,
            DatasetCase(
                case_id="case-1",
                input="where is my order?",
                expected_output="answer with delivery status",
            ),
            session_id="session-1",
            attempt_index=1,
        )
