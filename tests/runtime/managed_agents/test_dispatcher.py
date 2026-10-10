"""Protocol tests use the published Anthropic SDK, not dispatcher doubles."""

import asyncio
import base64
import json

import anthropic
import httpx2
import pytest

from veadk.runtime.managed_agents.dispatcher import EnvironmentWorkDispatcher


def item(number=1, session="session-1", secret=True):
    return {
        "id": f"work-{number}",
        "created_at": "2026-10-10T00:00:00Z",
        "data": {"id": session, "type": "session"},
        "environment_id": "env-1",
        "metadata": {},
        "secret": base64.urlsafe_b64encode(
            json.dumps({"sessions_token": f"scoped-{number}"}).encode()
        ).decode()
        if secret
        else None,
        "state": "starting",
        "type": "work",
    }


def heartbeat(stamp="stamp-1", **kwargs):
    return {
        "last_heartbeat": stamp,
        "lease_extended": True,
        "state": "active",
        "ttl_seconds": 90,
        "type": "work_heartbeat",
        **kwargs,
    }


class Protocol:
    def __init__(self, items=(), *, heartbeat_status=200, poll_status=None):
        self.items = list(items)
        self.requests = []
        self.heartbeat_status = heartbeat_status
        self.poll_status = poll_status
        self.poll_block = None

    async def __call__(self, request):
        self.requests.append(request)
        path = request.url.path
        if path.endswith("/poll"):
            if self.poll_block:
                await self.poll_block.wait()
            if self.poll_status:
                return httpx2.Response(
                    self.poll_status,
                    json={
                        "error": {"type": "authentication_error", "message": "rejected"}
                    },
                )
            return (
                httpx2.Response(200, json=self.items.pop(0))
                if self.items
                else httpx2.Response(204)
            )
        if path.endswith("/heartbeat"):
            return httpx2.Response(
                self.heartbeat_status,
                json=heartbeat()
                if self.heartbeat_status == 200
                else {"error": {"type": "lease_error", "message": "rejected"}},
            )
        return httpx2.Response(200, json=item())

    def paths(self, suffix):
        return [r for r in self.requests if r.url.path.endswith(suffix)]


def client(protocol):
    return anthropic.AsyncAnthropic(
        api_key="parent-key",
        auth_token="parent-token",
        base_url="https://ma.example",
        max_retries=0,
        default_headers={
            "authorization": "Bearer parent-custom",
            "x-api-key": "parent-custom-key",
            "X-Custom": "preserved",
            "X-Top-Account-Id": "test-account",
            "X-Runtime-Type": "test-runtime",
        },
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(protocol)),
    )


def dispatcher(c, handler, **kwargs):
    return EnvironmentWorkDispatcher(
        c,
        handler=handler,
        environment_id="env-1",
        environment_key="environment-key",
        worker_id="worker-1",
        **kwargs,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("account_work", [False, True])
async def test_wire_scope_ack_fence_and_stop(account_work):
    protocol = Protocol([item()])
    async with client(protocol) as c:

        async def handle(work, scoped):
            await scoped.beta.sessions.retrieve("session-1")

        d = dispatcher(c, handle, account_work=account_work)
        assert await d.run(max_items=1) == 1
        assert d.ready.is_set()
    assert len(protocol.paths("/ack")) == len(protocol.paths("/stop")) == 1
    poll = protocol.paths("/poll")[0]
    assert poll.headers["authorization"] == "Bearer environment-key"
    assert poll.url.params["block_ms"] == "999"
    assert poll.headers["Anthropic-Worker-ID"] == "worker-1"
    if account_work:
        assert poll.url.path == "/v1/model-work/poll"
    for request in protocol.requests:
        assert "x-api-key" not in request.headers
        assert request.headers["X-Custom"] == "preserved"
        assert request.headers["X-Top-Account-Id"] == "test-account"
        assert request.headers["X-Runtime-Type"] == "test-runtime"
        if not request.url.path.endswith("/poll"):
            assert request.headers["authorization"] == "Bearer scoped-1"
    assert (
        protocol.paths("/heartbeat")[0].url.params["expected_last_heartbeat"]
        == "NO_HEARTBEAT"
    )
    assert json.loads(protocol.paths("/stop")[0].content)["force"] is True


@pytest.mark.asyncio
async def test_same_session_fifo_and_concurrency_bound():
    protocol = Protocol([item(1), item(2), item(3, "session-2")])
    first = asyncio.Event()
    started = []
    async with client(protocol) as c:

        async def handle(work, scoped):
            started.append(work.id)
            if work.id == "work-1":
                await first.wait()

        d = dispatcher(c, handle)
        task = asyncio.create_task(d.run(max_items=3, max_concurrency=2))
        for _ in range(50):
            if len(protocol.paths("/ack")) >= 2:
                break
            await asyncio.sleep(0.01)
        assert started == ["work-1"]
        assert len(protocol.paths("/poll")) == 2
        first.set()
        assert await asyncio.wait_for(task, 2) == 3
    assert started.index("work-1") < started.index("work-2")


@pytest.mark.asyncio
async def test_drain_interrupts_poll_wait_and_preserves_accepted_handler():
    protocol = Protocol([item()])
    finished = asyncio.Event()
    started = asyncio.Event()
    async with client(protocol) as c:

        async def handle(*args):
            started.set()
            await finished.wait()

        d = dispatcher(c, handle)
        task = asyncio.create_task(d.run(max_concurrency=2))
        await asyncio.wait_for(started.wait(), 1)
        protocol.poll_block = asyncio.Event()
        await asyncio.sleep(0.3)
        d.drain()
        assert not task.done()
        finished.set()
        assert await asyncio.wait_for(task, 1) == 1
    assert len(protocol.paths("/stop")) == 1


@pytest.mark.asyncio
async def test_lease_loss_cancels_handler_without_stopping_new_owner():
    protocol = Protocol([item()], heartbeat_status=412)
    ran = []
    async with client(protocol) as c:

        async def handle(*args):
            ran.append(True)
            await asyncio.Event().wait()

        assert await dispatcher(c, handle).run(max_items=1) == 1
    assert not ran
    assert not protocol.paths("/stop")


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["poll", "heartbeat"])
async def test_authentication_failure_propagates_for_credential_refresh(phase):
    protocol = Protocol(
        [item()],
        heartbeat_status=401 if phase == "heartbeat" else 200,
        poll_status=401 if phase == "poll" else None,
    )
    async with client(protocol) as c:

        async def handle(*args):
            await asyncio.Event().wait()

        d = dispatcher(c, handle)
        with pytest.raises(anthropic.AuthenticationError):
            await asyncio.wait_for(d.run(max_items=1), 1)
        if phase == "poll":
            assert not d.ready.is_set()


@pytest.mark.asyncio
async def test_external_cancellation_waits_for_handler_cleanup_and_stop():
    protocol = Protocol([item()])
    started = asyncio.Event()
    cleaned = asyncio.Event()
    async with client(protocol) as c:

        async def handle(*args):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                await asyncio.sleep(0.01)
                cleaned.set()

        d = dispatcher(c, handle)
        task = asyncio.create_task(d.run(max_items=1))
        await asyncio.wait_for(started.wait(), 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert cleaned.is_set()
    assert len(protocol.paths("/stop")) == 1


@pytest.mark.asyncio
async def test_handler_failure_isolated_and_secret_details_not_logged(caplog):
    protocol = Protocol([item(1), item(2)])
    ran = []
    async with client(protocol) as c:

        async def handle(work, scoped):
            ran.append(work.id)
            if work.id == "work-1":
                raise RuntimeError("private-bearer-secret")

        assert await dispatcher(c, handle).run(max_items=2) == 2
    assert ran == ["work-1", "work-2"]
    assert len(protocol.paths("/stop")) == 2
    assert "private-bearer-secret" not in caplog.text


@pytest.mark.asyncio
async def test_account_poll_rejects_malformed_secret_without_logging_body(caplog):
    protocol = Protocol([item(secret=False)])
    async with client(protocol) as c:
        d = dispatcher(c, lambda *args: None, account_work=True)
        with pytest.raises(ValueError, match="malformed"):
            await d.run(max_items=1)
        assert not d.ready.is_set()
    assert not protocol.paths("/ack")


@pytest.mark.asyncio
async def test_heartbeat_echoes_timestamp_and_cancels_on_control_plane_stop(
    monkeypatch,
):
    from veadk.runtime.managed_agents import dispatcher as module

    monkeypatch.setattr(module, "HEARTBEAT_INTERVAL", 0.01)
    protocol = Protocol([item()])
    beats = 0
    original = protocol.__call__

    async def transport(request):
        nonlocal beats
        if request.url.path.endswith("/heartbeat"):
            protocol.requests.append(request)
            beats += 1
            return httpx2.Response(
                200,
                json=heartbeat(
                    f"stamp-{beats}", state="stopping" if beats == 2 else "active"
                ),
            )
        return await original(request)

    started, cleaned = asyncio.Event(), asyncio.Event()
    async with client(transport) as c:

        async def handle(*args):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cleaned.set()

        await dispatcher(c, handle).run(max_items=1)
    assert started.is_set() and cleaned.is_set()
    assert (
        protocol.paths("/heartbeat")[1].url.params["expected_last_heartbeat"]
        == "stamp-1"
    )
    assert len(protocol.paths("/stop")) == 1


@pytest.mark.asyncio
async def test_transient_heartbeat_failures_expire_lease_without_stop(monkeypatch):
    from veadk.runtime.managed_agents import dispatcher as module

    monkeypatch.setattr(module, "HEARTBEAT_INTERVAL", 0.01)
    monkeypatch.setattr(module, "LEASE_TTL", 0.03)
    protocol = Protocol([item()], heartbeat_status=503)
    async with client(protocol) as c:

        async def handle(*args):
            pytest.fail("unfenced lease must not run a handler")

        await asyncio.wait_for(dispatcher(c, handle).run(max_items=1), 1)
    assert len(protocol.paths("/heartbeat")) > 1
    assert not protocol.paths("/stop")


@pytest.mark.asyncio
async def test_empty_poll_marks_ready_but_claims_no_work():
    protocol = Protocol()
    async with client(protocol) as c:

        async def handle(*args):
            pytest.fail("204 is not Work")

        d = dispatcher(c, handle)
        task = asyncio.create_task(d.run())
        await asyncio.wait_for(d.ready.wait(), 1)
        d.drain()
        assert await asyncio.wait_for(task, 1) == 0
    assert not protocol.paths("/ack")


@pytest.mark.asyncio
async def test_safe_poll_trace_reports_metadata_only(monkeypatch, caplog):
    monkeypatch.setenv("MANAGED_AGENT_POLL_TRACE", "true")
    caplog.set_level("INFO", logger="anthropic.managed_agent_poll")
    protocol = Protocol([item()])
    async with client(protocol) as c:

        async def handle(*args):
            pass

        await dispatcher(c, handle, account_work=True).run(max_items=1)
    assert "poll_started" in caplog.text and "poll_completed" in caplog.text
    assert "scoped-1" not in caplog.text and "environment-key" not in caplog.text
    assert item()["secret"] not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("max_items,max_concurrency", [(0, 1), (1, 0), (-1, 2)])
async def test_invalid_limits_fail_before_poll(max_items, max_concurrency):
    protocol = Protocol()
    async with client(protocol) as c:
        with pytest.raises(ValueError):
            await dispatcher(c, lambda *args: None).run(
                max_items=max_items, max_concurrency=max_concurrency
            )
    assert not protocol.requests


@pytest.mark.asyncio
async def test_independent_sessions_execute_concurrently():
    protocol = Protocol([item(1, "session-1"), item(2, "session-2")])
    release = asyncio.Event()
    both = asyncio.Event()
    running = []
    async with client(protocol) as c:

        async def handle(work, scoped):
            running.append(work.id)
            if len(running) == 2:
                both.set()
            await release.wait()

        task = asyncio.create_task(
            dispatcher(c, handle).run(max_items=2, max_concurrency=2)
        )
        await asyncio.wait_for(both.wait(), 1)
        release.set()
        assert await task == 2


@pytest.mark.asyncio
async def test_heartbeat_auth_failure_interrupts_blocked_poll():
    protocol = Protocol([item()])
    original = protocol.__call__

    async def transport(request):
        if request.url.path.endswith("/heartbeat"):
            await asyncio.sleep(0.05)
            return httpx2.Response(401, json={"error": {"message": "rejected"}})
        response = await original(request)
        if request.url.path.endswith("/poll") and response.status_code == 200:
            protocol.poll_block = asyncio.Event()
        return response

    async with client(transport) as c:

        async def handle(*args):
            await asyncio.Event().wait()

        with pytest.raises(anthropic.AuthenticationError):
            await asyncio.wait_for(dispatcher(c, handle).run(max_concurrency=2), 1)


@pytest.mark.asyncio
async def test_nonterminal_unextended_lease_does_not_force_stop():
    protocol = Protocol([item()])
    original = protocol.__call__

    async def transport(request):
        if request.url.path.endswith("/heartbeat"):
            return httpx2.Response(200, json=heartbeat(lease_extended=False))
        return await original(request)

    async with client(transport) as c:

        async def handle(*args):
            pytest.fail("unextended lease cannot run")

        await dispatcher(c, handle).run(max_items=1)
    assert not protocol.paths("/stop")


@pytest.mark.asyncio
async def test_drain_interrupts_retry_backoff():
    protocol = Protocol(poll_status=503)
    async with client(protocol) as c:
        d = dispatcher(c, lambda *args: None)
        task = asyncio.create_task(d.run())
        for _ in range(20):
            if protocol.requests:
                break
            await asyncio.sleep(0.01)
        d.drain()
        assert await asyncio.wait_for(task, 0.5) == 0
        assert not d.ready.is_set()


@pytest.mark.asyncio
async def test_stop_auth_failure_propagates_and_releases_session_barrier():
    protocol = Protocol([item()])
    original = protocol.__call__

    async def transport(request):
        if request.url.path.endswith("/stop"):
            return httpx2.Response(403, json={"error": {"message": "rejected"}})
        return await original(request)

    async with client(transport) as c:

        async def handle(*args):
            pass

        d = dispatcher(c, handle)
        with pytest.raises(anthropic.PermissionDeniedError):
            await d.run(max_items=1)
        assert not d._session_tails


@pytest.mark.asyncio
async def test_environment_poll_uses_official_generated_raw_api(monkeypatch):
    protocol = Protocol([item()])
    async with client(protocol) as sdk:
        resource_type = type(sdk.beta.environments.work.with_raw_response)
        original = resource_type.__init__
        calls = []

        def wrap(resource, work):
            original(resource, work)
            poll = resource.poll

            async def record(*args, **kwargs):
                calls.append((args, kwargs))
                return await poll(*args, **kwargs)

            resource.poll = record

        monkeypatch.setattr(resource_type, "__init__", wrap)

        async def handle(*args):
            pass

        await dispatcher(sdk, handle).run(max_items=1)
    assert len(calls) == 1
    assert calls[0][0] == ("env-1",)
    assert calls[0][1]["anthropic_worker_id"] == "worker-1"
    assert calls[0][1]["block_ms"] == 999


@pytest.mark.asyncio
@pytest.mark.parametrize("status,body", [(200, {}), (200, None), (202, {})])
async def test_environment_poll_rejects_invalid_response_before_readiness(status, body):
    async def respond(request):
        if body is None:
            return httpx2.Response(status, text="not Work")
        return httpx2.Response(status, json=body)

    async with client(respond) as sdk:
        d = dispatcher(sdk, lambda *args: None)
        with pytest.raises(ValueError, match="Work poll returned"):
            await d.run(max_items=1)
        assert not d.ready.is_set()
