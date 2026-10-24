# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.

import asyncio
import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import anthropic
import pytest
from veadk.runtime.managed_agents.dispatcher import EnvironmentWorkDispatcher


def _secret(token: str) -> str:
    payload = json.dumps({"sessions_token": token}).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def _work(environment_id: str) -> dict[str, object]:
    return {
        "id": f"work_{environment_id}",
        "type": "work",
        "environment_id": environment_id,
        "data": {"type": "session", "id": f"session_{environment_id}"},
        "metadata": {},
        "runtime_type": "codex",
        "state": "starting",
        "secret": _secret("session-token"),
        "created_at": "2026-09-16T00:00:00Z",
    }


class _Service(ThreadingHTTPServer):
    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), _Handler)
        self.requests: list[dict[str, object]] = []
        self.drain = False
        self.long_poll_started = threading.Event()
        self.release_long_poll = threading.Event()


class _Handler(BaseHTTPRequestHandler):
    server: _Service

    def log_message(self, *_args: object) -> None:
        return

    def _record(self, body: object = None) -> None:
        self.server.requests.append(
            {
                "method": self.command,
                "path": self.path,
                "headers": {key.lower(): value for key, value in self.headers.items()},
                "body": body,
            }
        )

    def _send(self, value: object, status: int = 200) -> None:
        payload = json.dumps(value).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(payload)))
        self.end_headers()
        try:
            self.wfile.write(payload)
        except BrokenPipeError:
            pass

    def do_GET(self) -> None:
        self._record()
        if "/work/poll" not in self.path and not self.path.startswith(
            "/v1/model-work/poll"
        ):
            self._send({}, 404)
            return
        if self.server.drain:
            self.server.long_poll_started.set()
            self.server.release_long_poll.wait(timeout=5)
            self._send({}, 204)
            return
        environment_id = (
            "env_account"
            if self.path.startswith("/v1/model-work/poll")
            else "env_direct"
        )
        self._send(_work(environment_id))

    def do_POST(self) -> None:
        length = int(self.headers.get("content-length", "0"))
        body = json.loads(self.rfile.read(length)) if length else {}
        self._record(body)
        path = self.path.split("?", 1)[0]
        environment_id = path.split("/")[3]
        if path.endswith("/heartbeat"):
            self._send(
                {
                    "type": "work_heartbeat",
                    "state": "active",
                    "last_heartbeat": "2026-09-16T00:00:01Z",
                    "lease_extended": True,
                    "ttl_seconds": 2,
                }
            )
            return
        if path.endswith(("/ack", "/stop")):
            value = _work(environment_id)
            value["state"] = "stopped" if path.endswith("/stop") else "active"
            self._send(value)
            return
        self._send({}, 404)


@pytest.fixture
def service():
    instance = _Service()
    thread = threading.Thread(target=instance.serve_forever, daemon=True)
    thread.start()
    try:
        yield instance
    finally:
        instance.release_long_poll.set()
        instance.shutdown()
        instance.server_close()
        thread.join(timeout=2)


def _client(service: _Service, token: str) -> anthropic.AsyncAnthropic:
    return anthropic.AsyncAnthropic(
        base_url=f"http://127.0.0.1:{service.server_port}",
        auth_token=token,
        http_client=anthropic.DefaultAsyncHttpxClient(trust_env=False),
        timeout=5,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("account_work", [False, True], ids=["environment", "account"])
async def test_runtime_type_dispatcher_lifecycle(
    service: _Service, account_work: bool
) -> None:
    handled: list[str] = []

    async def handler(item: object, _client: anthropic.AsyncAnthropic) -> None:
        assert getattr(item, "runtime_type") == "codex"
        handled.append(getattr(item, "id"))
        await asyncio.sleep(0.05)

    async with _client(
        service, "account-token" if account_work else "environment-token"
    ) as client:
        dispatcher = EnvironmentWorkDispatcher(
            client,
            handler=handler,
            environment_id="" if account_work else "env_direct",
            environment_key="account-token" if account_work else "environment-token",
            account_work=account_work,
            worker_id="runtime-type-test",
            extra_headers={"X-Runtime-Type": "codex"},
        )
        assert await dispatcher.run(max_items=1) == 1

    environment_id = "env_account" if account_work else "env_direct"
    paths = [str(request["path"]) for request in service.requests]
    assert handled == [f"work_{environment_id}"]
    assert any(
        "/work/poll" in path or path.startswith("/v1/model-work/poll") for path in paths
    )
    assert any("/ack?" in path for path in paths)
    assert any("/heartbeat?" in path for path in paths)
    assert any("/stop?" in path for path in paths)
    assert all(
        request["headers"].get("x-runtime-type") == "codex"
        for request in service.requests
    )


@pytest.mark.asyncio
async def test_runtime_type_dispatcher_drain_cancels_empty_poll(
    service: _Service,
) -> None:
    service.drain = True

    async def handler(_item: object, _client: anthropic.AsyncAnthropic) -> None:
        raise AssertionError("empty queue produced work")

    async with _client(service, "environment-token") as client:
        dispatcher = EnvironmentWorkDispatcher(
            client,
            handler=handler,
            environment_id="env_direct",
            environment_key="environment-token",
            extra_headers={"X-Runtime-Type": "codex"},
        )
        task = asyncio.create_task(dispatcher.run())
        assert await asyncio.to_thread(service.long_poll_started.wait, 2)
        dispatcher.drain()
        assert await asyncio.wait_for(task, timeout=2) == 0

    assert service.requests[0]["headers"].get("x-runtime-type") == "codex"
