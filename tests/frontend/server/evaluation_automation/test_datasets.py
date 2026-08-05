from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from frontend.server.evaluation_automation import datasets


@pytest.mark.asyncio
async def test_ensure_feedback_sets_creates_good_and_bad_sets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str]] = []

    class _FakeDatasetsClient:
        def __init__(self, post: Any, *, project_name: str) -> None:
            assert project_name == "default"
            self.post = post

        async def ensure_feedback_set(
            self, agent_name: str, rating: str
        ) -> SimpleNamespace:
            calls.append((agent_name, rating))
            return SimpleNamespace(name=f"{agent_name}_{rating}_case")

    async def openapi_post(**kwargs: Any) -> dict[str, Any]:
        assert kwargs["region"] == "cn-beijing"
        return {}

    monkeypatch.setattr(
        datasets,
        "AgentKitEvaluationDatasetsClient",
        _FakeDatasetsClient,
    )

    created = await datasets.ensure_feedback_sets(
        openapi_post=openapi_post,
        region="cn-beijing",
        project_name="default",
        agent_name="客服助手",
    )

    assert created == ["客服助手_good_case", "客服助手_bad_case"]
    assert calls == [("客服助手", "good"), ("客服助手", "bad")]
