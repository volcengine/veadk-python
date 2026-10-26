from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from veadk.runtime.managed_agents import identity as runtime_identity


@pytest.fixture(autouse=True)
def isolate_gateway_credentials(monkeypatch):
    monkeypatch.setattr(runtime_identity, "_gateway_providers", {})


class FakeIdentity:
    def __init__(self, key: Any = None, fail=None, runtime_id="runtime-id"):
        self.key = SimpleNamespace(api_key="secret") if key is None else key
        self.fail = fail
        self.runtime_id = runtime_id
        self.calls = 0

    def get_workload_access_token(self, *, workload_name):
        assert workload_name == self.runtime_id
        return SimpleNamespace(workload_access_token="token")

    def get_api_key(self, *, provider_name, agent_identity_token):
        self.calls += 1
        assert provider_name == f"{self.runtime_id}-ma"
        assert agent_identity_token == "token"
        if self.fail:
            raise self.fail
        return self.key


@pytest.mark.asyncio
async def test_missing_workload_is_authentication_failure_not_missing_provider():
    class MissingWorkload(FakeIdentity):
        def get_workload_access_token(self, *, workload_name):
            raise RuntimeError("Workload NotFound raw-secret")

    fake = MissingWorkload()
    provider = runtime_identity.RuntimeCredentialProvider(
        runtime_id="runtime-id",
        client_factory=lambda: fake,
    )
    with pytest.raises(runtime_identity.RuntimeIdentityError) as info:
        await provider.get()
    assert info.value.category == "authentication_failed"
    assert fake.calls == 0
    assert "raw-secret" not in str(info.value)


@pytest.mark.asyncio
async def test_identity_extracts_sdk_response_and_caches_in_memory():
    fake = FakeIdentity()
    provider = runtime_identity.RuntimeCredentialProvider(
        runtime_id="runtime-id",
        client_factory=lambda: fake,
    )
    assert await provider.get() == "secret"
    assert await provider.get() == "secret"
    assert fake.calls == 1
    assert "secret" not in repr(provider)


def test_gateway_key_survives_elapsed_time_and_refreshes_explicitly(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(runtime_identity.time, "monotonic", lambda: now[0])
    fake = FakeIdentity(key="first-key")
    provider = runtime_identity.RuntimeCredentialProvider(
        runtime_id="runtime-id", client_factory=lambda: fake
    )
    assert provider.get_sync() == "first-key"
    for elapsed in (30, 60, 3600, 86400):
        now[0] += elapsed
        assert provider.get_sync() == "first-key"
    assert fake.calls == 1
    fake.key = "rotated-key"
    assert provider.get_sync(force_refresh=True) == "rotated-key"
    assert fake.calls == 2
    fake.fail = RuntimeError("AccessDenied raw-secret")
    with pytest.raises(runtime_identity.RuntimeIdentityError):
        provider.get_sync(force_refresh=True)
    with pytest.raises(runtime_identity.RuntimeIdentityError):
        provider.get_sync()
    assert fake.calls == 4, "Failed refresh must not fall back to a stale key"


def test_gateway_credentials_are_shared_during_concurrent_first_use(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    fake = FakeIdentity()
    monkeypatch.setattr(runtime_identity, "IdentityClient", lambda **kwargs: fake)
    barrier = Barrier(8)

    def resolve(_):
        barrier.wait(timeout=10)
        provider = runtime_identity.get_runtime_credential_provider(
            runtime_id="runtime-id"
        )
        return provider.get_sync()

    with ThreadPoolExecutor(max_workers=8) as executor:
        assert list(executor.map(resolve, range(8))) == ["secret"] * 8
    assert fake.calls == 1


def test_gateway_credentials_are_isolated_by_runtime_and_region(monkeypatch):
    calls = []

    class Identity:
        def __init__(self, *, region):
            self.region = region

        def get_workload_access_token(self, *, workload_name):
            return SimpleNamespace(workload_access_token=workload_name)

        def get_api_key(self, *, provider_name, agent_identity_token):
            calls.append((agent_identity_token, self.region))
            return f"{provider_name}-{self.region}"

    monkeypatch.setattr(runtime_identity, "IdentityClient", Identity)
    references = [
        ("runtime-a", "cn-beijing"),
        ("runtime-b", "cn-beijing"),
        ("runtime-a", "cn-shanghai"),
    ]
    for _ in range(2):
        for runtime_id, region in references:
            provider = runtime_identity.get_runtime_credential_provider(
                runtime_id=runtime_id, region=region
            )
            assert provider.get_sync() == f"{runtime_id}-ma-{region}"
    assert calls == references


@pytest.mark.asyncio
async def test_identity_error_is_sanitized():
    fake = FakeIdentity(fail=RuntimeError("AccessDenied raw-secret"))
    provider = runtime_identity.RuntimeCredentialProvider(
        runtime_id="runtime-id",
        client_factory=lambda: fake,
    )
    with pytest.raises(runtime_identity.RuntimeIdentityError) as info:
        await provider.get()
    assert info.value.category == "authentication_failed"
    assert "raw-secret" not in str(info.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "raw",
    [
        "value",
        {"ApiKey": "value"},
        {"api_key": "value"},
        SimpleNamespace(api_key="value"),
    ],
)
async def test_sdk_key_shapes(raw):
    fake = FakeIdentity(key=raw)
    provider = runtime_identity.RuntimeCredentialProvider(
        runtime_id="runtime-id",
        client_factory=lambda: fake,
    )
    assert await provider.get() == "value"
    provider.invalidate()
    assert await provider.get() == "value"
    assert fake.calls == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message, category, calls",
    [
        ("Provider AccessDenied secret", "authentication_failed", 1),
        ("Provider NotFound secret", "provider_not_found", 1),
        ("ConnectionError secret", "network_error", 3),
    ],
)
async def test_identity_classifies_and_bounds_retries(message, category, calls):
    fake = FakeIdentity(fail=RuntimeError(message))
    provider = runtime_identity.RuntimeCredentialProvider(
        runtime_id="runtime-id",
        client_factory=lambda: fake,
    )
    with pytest.raises(runtime_identity.RuntimeIdentityError) as info:
        await provider.get()
    assert info.value.category == category
    assert "secret" not in str(info.value)
    assert fake.calls == calls


@pytest.mark.asyncio
async def test_existing_client_uses_identity_key_for_sync_and_async_sdk(monkeypatch):
    import sys

    monkeypatch.setitem(
        sys.modules, "veadk.runtime.managed_agents.identity", runtime_identity
    )
    monkeypatch.setenv("MA_RUNTIME_ID", "runtime-id")
    monkeypatch.delenv("MA_IDENTITY_PROVIDER_NAME", raising=False)
    for name in (
        "ANTHROPIC_ENVIRONMENT_KEY",
        "ANTHROPIC_API_KEY",
        "SANDBOX_BEARER_TOKEN",
        "SANDBOX_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    fake = FakeIdentity()
    monkeypatch.setattr(runtime_identity, "IdentityClient", lambda **kwargs: fake)
    from veadk.integrations.mpa.session_client import SelfHostSandboxClient

    client = SelfHostSandboxClient(base_url="https://example.test")
    try:
        assert client.bearer_token == "secret"
        assert client.client.auth_token == "secret"
        assert fake.calls == 1
        async with client.create_async_client() as sdk:
            assert sdk.auth_token == "secret"
        peer = SelfHostSandboxClient(base_url="https://example.test")
        try:
            assert peer.bearer_token == "secret"
            assert fake.calls == 1
        finally:
            peer.client.close()
        assert "ANTHROPIC_ENVIRONMENT_KEY" not in __import__("os").environ
    finally:
        client.client.close()


def test_explicit_work_token_keeps_existing_authentication(monkeypatch):
    import sys

    monkeypatch.setitem(
        sys.modules, "veadk.runtime.managed_agents.identity", runtime_identity
    )
    monkeypatch.setenv("MA_RUNTIME_ID", "runtime-id")

    def unexpected_identity(**kwargs):
        raise AssertionError("Explicit Work tokens must not call Identity")

    monkeypatch.setattr(runtime_identity, "IdentityClient", unexpected_identity)
    from veadk.integrations.mpa.session_client import SelfHostSandboxClient

    client = SelfHostSandboxClient(
        base_url="https://example.test", bearer_token="work-token"
    )
    try:
        assert client.bearer_token == "work-token"
    finally:
        client.client.close()


@pytest.mark.parametrize(
    "environment, expected",
    [
        (
            {
                "AGENTKIT_RUNTIME_ID": "explicit-agentkit",
                "MA_RUNTIME_ID": "explicit-ma",
                "MODEL_AGENT_CLIENT_REQ_ID": "agentkit/platform-runtime",
            },
            "explicit-agentkit",
        ),
        (
            {
                "MA_RUNTIME_ID": "explicit-ma",
                "MODEL_AGENT_CLIENT_REQ_ID": "agentkit/platform-runtime",
            },
            "explicit-ma",
        ),
        (
            {
                "AGENTKIT_RUNTIME_ID": "   ",
                "MA_RUNTIME_ID": "explicit-ma",
                "MODEL_AGENT_CLIENT_REQ_ID": "agentkit/platform-runtime",
            },
            "explicit-ma",
        ),
        ({"MODEL_AGENT_CLIENT_REQ_ID": "agentkit/r-yev123"}, "r-yev123"),
        ({"MODEL_AGENT_CLIENT_REQ_ID": "veadk/0.5.0"}, ""),
        ({"MODEL_AGENT_CLIENT_REQ_ID": "agentkit/"}, ""),
        ({"MODEL_AGENT_CLIENT_REQ_ID": "agentkit/r-one/extra"}, ""),
        ({"MODEL_AGENT_CLIENT_REQ_ID": "prefix-agentkit/r-one"}, ""),
    ],
)
def test_runtime_id_environment_resolution_is_strict_and_prioritized(
    monkeypatch, environment, expected
):
    for name in (
        "AGENTKIT_RUNTIME_ID",
        "MA_RUNTIME_ID",
        "MODEL_AGENT_CLIENT_REQ_ID",
    ):
        monkeypatch.delenv(name, raising=False)
    for name, value in environment.items():
        monkeypatch.setenv(name, value)

    from veadk.integrations.mpa.session_client import _runtime_id_from_environment

    assert _runtime_id_from_environment() == expected


def test_platform_client_request_id_enables_runtime_identity(monkeypatch):
    import sys

    monkeypatch.setitem(
        sys.modules, "veadk.runtime.managed_agents.identity", runtime_identity
    )
    monkeypatch.delenv("AGENTKIT_RUNTIME_ID", raising=False)
    monkeypatch.delenv("MA_RUNTIME_ID", raising=False)
    monkeypatch.setenv("MODEL_AGENT_CLIENT_REQ_ID", "agentkit/r-platform")
    for name in (
        "ANTHROPIC_ENVIRONMENT_KEY",
        "ANTHROPIC_API_KEY",
        "SANDBOX_BEARER_TOKEN",
        "SANDBOX_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    fake = FakeIdentity(runtime_id="r-platform")
    monkeypatch.setattr(runtime_identity, "IdentityClient", lambda **kwargs: fake)
    from veadk.integrations.mpa.session_client import SelfHostSandboxClient

    client = SelfHostSandboxClient(base_url="https://example.test")
    try:
        assert client._identity_credentials.runtime_id == "r-platform"
        assert client.bearer_token == "secret"
    finally:
        client.client.close()


@pytest.mark.parametrize(
    "key_name",
    [
        "ANTHROPIC_ENVIRONMENT_KEY",
        "ANTHROPIC_API_KEY",
        "SANDBOX_BEARER_TOKEN",
        "SANDBOX_API_KEY",
    ],
)
def test_environment_key_skips_identity(monkeypatch, key_name):
    import sys

    monkeypatch.setitem(
        sys.modules, "veadk.runtime.managed_agents.identity", runtime_identity
    )
    for name in (
        "ANTHROPIC_ENVIRONMENT_KEY",
        "ANTHROPIC_API_KEY",
        "SANDBOX_BEARER_TOKEN",
        "SANDBOX_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv(key_name, "Bearer supplied-environment-key")
    monkeypatch.setenv("MA_RUNTIME_ID", "runtime-id")

    def unexpected_identity(**kwargs):
        raise AssertionError("Environment keys must not call Identity")

    monkeypatch.setattr(runtime_identity, "IdentityClient", unexpected_identity)
    from veadk.integrations.mpa.session_client import SelfHostSandboxClient

    client = SelfHostSandboxClient(base_url="https://example.test")
    try:
        assert client.client.auth_token == "supplied-environment-key"
    finally:
        client.client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("auth_status", [401, 403])
async def test_transport_pairs_identity_header_with_sdk_work_lease(
    monkeypatch, auth_status
):
    import sys
    from typing import Dict

    import anthropic
    import httpx2
    from veadk.runtime.managed_agents.dispatcher import scoped_client

    monkeypatch.setitem(
        sys.modules, "veadk.runtime.managed_agents.identity", runtime_identity
    )
    monkeypatch.setenv("MA_RUNTIME_ID", "runtime-id")
    monkeypatch.delenv("MA_IDENTITY_PROVIDER_NAME", raising=False)
    for name in (
        "ANTHROPIC_ENVIRONMENT_KEY",
        "ANTHROPIC_API_KEY",
        "SANDBOX_BEARER_TOKEN",
        "SANDBOX_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    fake = FakeIdentity(key="first-key")
    monkeypatch.setattr(runtime_identity, "IdentityClient", lambda **kwargs: fake)
    sent = []
    response_status = [200]

    def respond(request):
        sent.append(dict(request.headers))
        return httpx2.Response(response_status[0], json={"ok": True})

    sync_http = anthropic.DefaultHttpxClient
    async_http = anthropic.DefaultAsyncHttpxClient
    monkeypatch.setattr(
        anthropic,
        "DefaultHttpxClient",
        lambda **kwargs: sync_http(transport=httpx2.MockTransport(respond), **kwargs),
    )
    monkeypatch.setattr(
        anthropic,
        "DefaultAsyncHttpxClient",
        lambda **kwargs: async_http(transport=httpx2.MockTransport(respond), **kwargs),
    )
    from veadk.integrations.mpa.session_client import SelfHostSandboxClient

    client = SelfHostSandboxClient(base_url="https://example.test")
    try:
        client.client.get("/v1/agents", cast_to=Dict[str, bool])
        assert sent[-1]["x-api-key"] == "first-key"
        assert "authorization" not in sent[-1]
        async with client.create_async_client() as sdk:
            poll = scoped_client(sdk, client.bearer_token)
            await poll.get("/v1/model-work/poll", cast_to=Dict[str, bool])
            assert sent[-1]["x-api-key"] == "first-key"
            assert "authorization" not in sent[-1]
            work = scoped_client(sdk, "work-lease")
            await work.get("/v1/sessions/session-id", cast_to=Dict[str, bool])
            assert sent[-1]["x-api-key"] == "first-key"
            assert sent[-1]["authorization"] == "Bearer work-lease"
            fake.key = "rotated-key"
            response_status[0] = auth_status
            with pytest.raises(anthropic.APIStatusError):
                await work.get("/v1/sessions/session-id", cast_to=Dict[str, bool])
            response_status[0] = 200
            await work.get("/v1/sessions/session-id", cast_to=Dict[str, bool])
            assert sent[-1]["x-api-key"] == "rotated-key"
            assert sent[-1]["authorization"] == "Bearer work-lease"
            assert fake.calls == 2
        client.client.get("/v1/agents", cast_to=Dict[str, bool])
        assert sent[-1]["x-api-key"] == "rotated-key"
        assert fake.calls == 2
    finally:
        client.client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "volcengine_region, region, expected",
    [
        ("cn-shanghai", "cn-guangzhou", "cn-shanghai"),
        (None, "cn-guangzhou", "cn-guangzhou"),
        ("", "cn-guangzhou", "cn-guangzhou"),
        (None, None, "cn-beijing"),
    ],
)
async def test_session_model_key_uses_configured_identity_region(
    monkeypatch, volcengine_region, region, expected
):
    monkeypatch.setenv("AGENTKIT_RUNTIME_ID", "runtime-id")
    for name, value in (("VOLCENGINE_REGION", volcengine_region), ("REGION", region)):
        monkeypatch.delenv(name, raising=False)
        if value is not None:
            monkeypatch.setenv(name, value)
    regions = []

    class ModelIdentity(FakeIdentity):
        def __init__(self, *, region):
            super().__init__()
            regions.append(region)

        def get_api_key(self, **kwargs):
            return "test-model-key"

    monkeypatch.setattr(runtime_identity, "IdentityClient", ModelIdentity)
    cache = runtime_identity.SessionModelCredentials()
    assert (
        await cache.get({"ark_api_key_provider": "ma-ark-" + "a" * 52})
        == "test-model-key"
    )
    assert regions == [expected]


@pytest.mark.asyncio
async def test_session_model_key_lru_isolation_and_failure(monkeypatch):
    monkeypatch.setenv("AGENTKIT_RUNTIME_ID", "runtime-id")
    calls = []

    class ModelIdentity(FakeIdentity):
        def get_api_key(self, *, provider_name, agent_identity_token):
            calls.append(provider_name)
            if provider_name == "ma-ark-" + "d" * 52:
                raise RuntimeError("AccessDenied raw-secret")
            return "key-for-" + provider_name

    cache = runtime_identity.SessionModelCredentials(
        capacity=2, client_factory=ModelIdentity
    )
    a, b, c, d = [{"ark_api_key_provider": "ma-ark-" + ch * 52} for ch in "abcd"]
    assert await cache.get(a) != await cache.get(b)
    assert await cache.get(a) == "key-for-" + a["ark_api_key_provider"]
    await cache.get(c)
    await cache.get(b)
    assert calls == [
        a["ark_api_key_provider"],
        b["ark_api_key_provider"],
        c["ark_api_key_provider"],
        b["ark_api_key_provider"],
    ]
    assert len(cache._providers) == 2
    with pytest.raises(
        runtime_identity.RuntimeIdentityError, match="missing_provider_reference"
    ) as error:
        await cache.get({})
    assert error.value.category == "missing_provider_reference"
    assert not error.value.retryable
    for _ in range(2):
        with pytest.raises(
            runtime_identity.RuntimeIdentityError, match="authentication_failed"
        ) as error:
            await cache.get(d)
        assert "raw-secret" not in str(error.value)
    assert calls[-2:] == [d["ark_api_key_provider"]] * 2
    with pytest.raises(
        runtime_identity.RuntimeIdentityError, match="invalid_provider_reference"
    ):
        await cache.get({"ark_api_key_provider": "runtime-id-ma"})
    monkeypatch.delenv("AGENTKIT_RUNTIME_ID")
    monkeypatch.delenv("MA_RUNTIME_ID", raising=False)
    monkeypatch.delenv("MODEL_AGENT_CLIENT_REQ_ID", raising=False)
    with pytest.raises(
        runtime_identity.RuntimeIdentityError, match="missing_workload_identity"
    ):
        await cache.get(a)


@pytest.mark.asyncio
async def test_session_model_key_default_capacity_and_one_hour_ttl(monkeypatch):
    import base64

    monkeypatch.setenv("AGENTKIT_RUNTIME_ID", "runtime-id")
    now = [100.0]
    monkeypatch.setattr(runtime_identity.time, "monotonic", lambda: now[0])
    calls = []

    class ModelIdentity(FakeIdentity):
        def get_api_key(self, *, provider_name, agent_identity_token):
            calls.append(provider_name)
            return "test-model-key"

    cache = runtime_identity.SessionModelCredentials(client_factory=ModelIdentity)
    assert cache.capacity == 2000

    def session(index):
        digest = (
            base64.b32encode(index.to_bytes(32, "big")).decode().rstrip("=").lower()
        )
        return {"ark_api_key_provider": "ma-ark-" + digest}

    first = session(0)
    await cache.get(first)
    now[0] += 3599
    await cache.get(first)
    assert len(calls) == 1
    now[0] += 1
    await cache.get(first)
    assert len(calls) == 2, "TTL expires at one hour; reads must not extend it"
    for index in range(1, 2000):
        await cache.get(session(index))
    assert len(cache._providers) == 2000
    await cache.get(first)
    await cache.get(session(2000))
    assert len(cache._providers) == 2000
    assert ("runtime-id", first["ark_api_key_provider"]) in cache._providers
    assert ("runtime-id", session(1)["ark_api_key_provider"]) not in cache._providers


@pytest.mark.asyncio
async def test_mcp_identity_headers_use_workload_and_cache_without_model_state(
    monkeypatch,
):
    monkeypatch.setenv("MA_RUNTIME_ID", "mcp-runtime")
    name = "user-orders-key"
    calls = []

    class Identity:
        def get_workload_access_token(self, *, workload_name):
            assert workload_name == "mcp-runtime"
            return SimpleNamespace(workload_access_token="workload-token")

        def get_api_key(self, *, provider_name, agent_identity_token, pool_name):
            assert pool_name == "team-pool"
            calls.append(provider_name)
            assert provider_name == name and agent_identity_token == "workload-token"
            return "mcp-private-key"

    headers = runtime_identity.MCPIdentityHeaders(
        {"Name": name, "PoolName": "team-pool", "MCPServerName": "orders"},
        client_factory=Identity,
    )
    await headers.prepare()
    assert headers(None) == {"Authorization": "Bearer mcp-private-key"}
    await headers.prepare()
    assert calls == [name]
    assert "mcp-private-key" not in repr(headers)
    with pytest.raises(runtime_identity.RuntimeIdentityError):
        runtime_identity.RuntimeCredentialProvider(
            runtime_id="mcp-runtime", provider_name=name
        )


@pytest.mark.asyncio
async def test_mcp_identity_failure_does_not_fall_back(monkeypatch):
    monkeypatch.setenv("MA_RUNTIME_ID", "mcp-runtime")

    class Denied:
        def get_workload_access_token(self, **kwargs):
            raise RuntimeError("403 sensitive-key")

    headers = runtime_identity.MCPIdentityHeaders(
        {
            "Name": "user-orders-key",
            "PoolName": "default",
            "MCPServerName": "orders",
        },
        client_factory=Denied,
    )
    with pytest.raises(runtime_identity.RuntimeIdentityError) as caught:
        await headers.prepare()
    assert "sensitive-key" not in str(caught.value)
    assert caught.value.category == "authentication_failed"
    with pytest.raises(runtime_identity.RuntimeIdentityError):
        runtime_identity.MCPIdentityHeaders(
            {"type": "api_key", "api_key": "raw-secret"}
        )


def test_identity_client_forwards_user_pool_to_api():
    from veadk.integrations.ve_identity.identity_client import IdentityClient

    requests = []

    class API:
        def get_resource_api_key(self, request):
            requests.append(request.to_dict())
            return SimpleNamespace(api_key="synthetic-key")

    client = SimpleNamespace(_api_client=API())
    key = IdentityClient.get_api_key.__wrapped__(
        client,
        provider_name="user-provider",
        pool_name="team-pool",
        agent_identity_token="token",
    )
    assert key == "synthetic-key"
    assert requests == [
        {
            "provider_name": "user-provider",
            "pool_name": "team-pool",
            "identity_token": "token",
        }
    ]


@pytest.mark.asyncio
async def test_local_worker_requires_explicit_model_source_and_never_bypasses_identity(
    monkeypatch,
):
    from veadk.runtime.managed_agents.worker import resolve_session_model_key

    monkeypatch.setenv("MODEL_AGENT_API_KEY", "local-model-fixture")
    monkeypatch.delenv("MANAGED_AGENT_MODEL_CREDENTIAL_SOURCE", raising=False)
    with pytest.raises(
        runtime_identity.RuntimeIdentityError, match="missing_provider_reference"
    ):
        await resolve_session_model_key({}, "default")
    monkeypatch.setenv("MANAGED_AGENT_MODEL_CREDENTIAL_SOURCE", "environment")
    assert await resolve_session_model_key({}, "default") == "local-model-fixture"
    with pytest.raises(
        runtime_identity.RuntimeIdentityError, match="missing_provider_reference"
    ):
        await resolve_session_model_key({}, "agentkit_runtime")
    with pytest.raises(
        runtime_identity.RuntimeIdentityError, match="invalid_provider_reference"
    ):
        await resolve_session_model_key({"ark_api_key_provider": "invalid"}, "default")
    monkeypatch.delenv("MODEL_AGENT_API_KEY")
    with pytest.raises(
        runtime_identity.RuntimeIdentityError, match="missing_model_key"
    ):
        await resolve_session_model_key({}, "default")


@pytest.mark.asyncio
async def test_invalid_model_credential_source_fails_closed(monkeypatch):
    from veadk.runtime.managed_agents.worker import resolve_session_model_key

    monkeypatch.setenv("MANAGED_AGENT_MODEL_CREDENTIAL_SOURCE", "unknown")
    with pytest.raises(ValueError, match="credential source"):
        await resolve_session_model_key({}, "default")
