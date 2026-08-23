from __future__ import annotations

from collections.abc import Mapping

import pytest

from frontend.server.scenario_evaluation.composition import create_components
from frontend.server.scenario_evaluation.errors import ScenarioUnavailable
from frontend.server.scenario_evaluation.repository import (
    InMemoryScenarioEvaluationRepository,
    TosScenarioEvaluationRepository,
    UnavailableScenarioEvaluationRepository,
)


class _GeneratedRuntimeManager:
    async def create(self, project, *, environment, owner_id):  # type: ignore[no-untyped-def]
        raise AssertionError("runtime should not start during composition")

    async def run_case(self, handle, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("runtime should not run during composition")

    async def close(self, handle):  # type: ignore[no-untyped-def]
        raise AssertionError("runtime should not close during composition")


class _CredentialResolver:
    async def resolve(self, reference: str) -> str:
        raise AssertionError(
            f"credential should not resolve during composition: {reference}"
        )


def _components(
    *,
    studio: bool,
    storage_environment: Mapping[str, str] | None = None,
    storage_client_factory=None,  # type: ignore[no-untyped-def]
):
    return create_components(
        studio=studio,
        provider="volcengine",
        generated_runtime_manager=_GeneratedRuntimeManager(),
        credential_resolver=_CredentialResolver(),
        base_environment=lambda: {"SAFE_BASE": "enabled"},
        storage_environment=storage_environment,
        storage_client_factory=storage_client_factory,
    )


@pytest.mark.asyncio
async def test_studio_without_storage_fails_closed() -> None:
    components = _components(studio=True, storage_environment={})

    assert isinstance(
        components.repository,
        UnavailableScenarioEvaluationRepository,
    )
    with pytest.raises(ScenarioUnavailable, match="持久化存储"):
        await components.repository.list(
            agent_id="agent-1",
            record_type="candidate_version",  # type: ignore[arg-type]
        )


def test_local_frontend_uses_explicit_process_local_repository() -> None:
    components = _components(studio=False, storage_environment={})

    assert isinstance(components.repository, InMemoryScenarioEvaluationRepository)


def test_configured_studio_uses_tos_repository() -> None:
    components = _components(
        studio=True,
        storage_environment={
            "VEADK_STUDIO_TOS_BUCKET": "studio-bucket",
            "VEADK_STUDIO_TOS_REGION": "cn-beijing",
        },
        storage_client_factory=lambda: object(),
    )

    assert isinstance(components.repository, TosScenarioEvaluationRepository)
