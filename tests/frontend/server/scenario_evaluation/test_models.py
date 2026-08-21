from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from frontend.server.scenario_evaluation.models import (
    CandidateArtifact,
    CandidateVersion,
    CredentialReference,
    EvaluationDependencies,
)


def _artifact() -> CandidateArtifact:
    return CandidateArtifact(
        code_digest="sha256:code",
        topology_digest="sha256:topology",
        model_refs=("model-endpoint:v1",),
        prompt_refs=("prompt:assistant:v3",),
        tool_refs=("tool:search:v2",),
        skill_refs=("skill:answer:v1",),
        knowledge_refs=("knowledge:faq:v4",),
        memory_refs=("memory:profile:v2",),
        environment_refs=(
            CredentialReference(name="MODEL_API_KEY", reference="secret://model-key"),
        ),
    )


def test_candidate_version_serializes_strict_camel_case_and_is_frozen() -> None:
    candidate = CandidateVersion.model_validate(
        {
            "candidateId": "candidate-1",
            "agentId": "agent-1",
            "version": 3,
            "artifact": _artifact().model_dump(by_alias=True),
            "createdAt": "2026-08-14T12:00:00Z",
            "createdBy": "developer-1",
        }
    )

    assert candidate.model_dump(by_alias=True)["candidateId"] == "candidate-1"
    assert candidate.created_at == datetime(2026, 8, 14, 12, tzinfo=timezone.utc)
    with pytest.raises(ValidationError):
        candidate.version = 4


def test_candidate_version_rejects_unknown_fields_and_naive_timestamps() -> None:
    payload = {
        "candidateId": "candidate-1",
        "agentId": "agent-1",
        "version": 1,
        "artifact": _artifact().model_dump(by_alias=True),
        "createdAt": "2026-08-14T12:00:00",
        "createdBy": "developer-1",
        "qualityGateToken": "not-supported",
    }

    with pytest.raises(ValidationError):
        CandidateVersion.model_validate(payload)


def test_candidate_artifact_accepts_secret_references_but_rejects_secret_values() -> (
    None
):
    payload = _artifact().model_dump(by_alias=True)
    payload["environmentRefs"][0]["value"] = "must-not-be-persisted"

    with pytest.raises(ValidationError):
        CandidateArtifact.model_validate(payload)


def test_evaluation_dependencies_require_every_validity_dimension() -> None:
    dependencies = EvaluationDependencies(
        candidate_id="candidate-1",
        baseline_version_id="published-7",
        scene_version_ids=("scene-1:v2",),
        dataset_version_ids=("dataset-1:v4",),
        evaluator_version_ids=("evaluator-1:v3",),
        policy_version_id="policy-1:v5",
        environment_fingerprint="sha256:runtime",
    )

    assert dependencies.model_dump(by_alias=True) == {
        "candidateId": "candidate-1",
        "baselineVersionId": "published-7",
        "sceneVersionIds": ("scene-1:v2",),
        "datasetVersionIds": ("dataset-1:v4",),
        "evaluatorVersionIds": ("evaluator-1:v3",),
        "policyVersionId": "policy-1:v5",
        "environmentFingerprint": "sha256:runtime",
    }
