"""Verify the installed listener's public HTTP health and invocation routes."""

import httpx
import pytest

from veadk.runtime.managed_agents import health


@pytest.mark.asyncio
async def test_health_routes_without_business_identity(monkeypatch):
    for name in (
        "ANTHROPIC_ENVIRONMENT_KEY",
        "ANTHROPIC_BASE_URL",
        "MODEL_AGENT_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    async with health.app.router.lifespan_context(health.app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=health.app), base_url="http://runtime"
        ) as client:
            for path in ("/ping", "/health", "/readiness", "/liveness"):
                assert (await client.get(path)).status_code == 200
            response = await client.post(
                "/invoke",
                json={"work_id": "ignored"},
                headers={"x-api-key": "private-marker"},
            )
            assert response.status_code == 200
            assert response.json() == {"status": "ok"}
            assert "private-marker" not in response.text
