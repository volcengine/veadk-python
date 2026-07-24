# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
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

import json
from types import SimpleNamespace

import pytest

from veadk.configs.database_configs import TOSContextBucketConfig
from veadk.memory.long_term_memory import LongTermMemory
from veadk.memory.long_term_memory_backends import tos_context_bucket_backend
from veadk.memory.long_term_memory_backends.tos_context_bucket_backend import (
    TosContextBucketLTMBackend,
)


class _ServerError(Exception):
    def __init__(self, status_code: int):
        self.status_code = status_code


class _Client:
    def __init__(self):
        self.buckets: set[str] = set()
        self.context_sets: dict[str, SimpleNamespace] = {}
        self.created_memories: list[dict] = []
        self.search_output = SimpleNamespace(results=[])
        self.get_context_set_calls = 0

    def get_context_bucket(self, *, context_bucket_name, **_kwargs):
        if context_bucket_name not in self.buckets:
            raise _ServerError(404)

    def create_context_bucket(self, *, context_bucket_name, **_kwargs):
        self.buckets.add(context_bucket_name)

    def get_context_set(self, *, context_set_name, **_kwargs):
        self.get_context_set_calls += 1
        if context_set_name not in self.context_sets:
            raise _ServerError(404)
        return self.context_sets[context_set_name]

    def create_context_set(self, *, context_set_name, enable, scenes, **_kwargs):
        self.context_sets[context_set_name] = SimpleNamespace(
            enable=enable, scenes=scenes
        )

    def create_context_bucket_memory(self, **kwargs):
        self.created_memories.append(kwargs)

    def search_context_bucket_memory(self, **_kwargs):
        return self.search_output


@pytest.fixture
def client(monkeypatch):
    fake_client = _Client()
    monkeypatch.setattr(tos_context_bucket_backend, "TosServerError", _ServerError)
    # Give every test a clean credential baseline. Other test modules (e.g.
    # tests/test_cloud.py) set VOLCENGINE_ACCESS_KEY / VOLCENGINE_SECRET_KEY at
    # import time via os.environ (never restored), which leaks into this process
    # under pytest-xdist and would otherwise flip the IAM fallback tests into the
    # explicit-credentials branch. Tests that need credentials set them
    # explicitly, so clearing here keeps this file self-contained.
    for _var in (
        "VOLCENGINE_ACCESS_KEY",
        "VOLCENGINE_SECRET_KEY",
        "VOLCENGINE_SESSION_TOKEN",
    ):
        monkeypatch.delenv(_var, raising=False)

    def _make_client(*args, **kwargs):
        fake_client.init_args = args
        fake_client.init_kwargs = kwargs
        return fake_client

    monkeypatch.setattr(tos_context_bucket_backend, "TosClientV2", _make_client)
    # These tests exercise the backend logic against a fake client, so they must
    # not depend on the real `tos` SDK version. Bypass the ContextBucket support
    # probe here; the probe itself is covered by
    # `test_asserts_when_context_bucket_unsupported`.
    monkeypatch.setattr(
        tos_context_bucket_backend, "_assert_context_bucket_supported", lambda: None
    )
    # Default: pretend the VeFaaS IAM file supplies credentials so tests that
    # don't set explicit AK/SK don't touch the filesystem.
    monkeypatch.setattr(
        tos_context_bucket_backend,
        "get_credential_from_vefaas_iam",
        lambda: SimpleNamespace(
            access_key_id="iam-ak",
            secret_access_key="iam-sk",
            session_token="iam-sts",
        ),
    )
    return fake_client


def _backend(**kwargs) -> TosContextBucketLTMBackend:
    defaults = {
        "index": "agent-memory",
        "account_id": "2100000000",
        "tos_context_config": TOSContextBucketConfig(
            endpoint="tos.example.com",
            region="cn-beijing",
            control_endpoint="tosapi-controller.example.com",
        ),
    }
    defaults.update(kwargs)
    return TosContextBucketLTMBackend(**defaults)


def test_initialization_creates_missing_context_bucket(client):
    backend = _backend()

    assert backend.context_bucket_name == "agent-memory"
    assert client.buckets == {"agent-memory"}


def test_backend_requires_controller_configuration(client):
    with pytest.raises(ValueError, match="CONTROL_ENDPOINT"):
        TosContextBucketLTMBackend(index="agent-memory", account_id="2100000000")


def test_backend_rejects_invalid_context_bucket_name(client):
    with pytest.raises(ValueError, match="lowercase letters"):
        _backend(index="Agent_Memory")


def test_save_lazily_creates_and_caches_context_set(client):
    backend = _backend()
    event = json.dumps({"role": "user", "parts": [{"text": "I like Go."}]})

    assert backend.save_memory("user-1", [event]) is True
    assert backend.save_memory("user-1", [event]) is True

    assert client.context_sets["user-1"].scenes == ["memory"]
    assert client.get_context_set_calls == 1
    assert [memory["content"] for memory in client.created_memories] == [
        "I like Go.",
        "I like Go.",
    ]
    assert all(memory["infer"] is True for memory in client.created_memories)


def test_save_returns_false_when_tos_request_fails(client):
    backend = _backend()

    def fail(**_kwargs):
        raise RuntimeError("service unavailable")

    client.create_context_bucket_memory = fail

    assert backend.save_memory("user-1", ["plain text"]) is False


def test_save_rejects_existing_context_set_without_memory_scene(client):
    backend = _backend()
    client.context_sets["user-1"] = SimpleNamespace(enable=True, scenes=[])

    assert backend.save_memory("user-1", ["plain text"]) is False
    assert client.created_memories == []


def test_search_returns_extracted_memories_and_is_user_scoped(client):
    backend = _backend()
    client.search_output = SimpleNamespace(
        results=[
            SimpleNamespace(memory="User likes basketball."),
            SimpleNamespace(memory=None),
        ]
    )
    captured = {}

    def search(**kwargs):
        captured.update(kwargs)
        return client.search_output

    client.search_context_bucket_memory = search

    assert backend.search_memory("user-2", "hobbies", 3) == ["User likes basketball."]
    assert captured["context_set_name"] == "user-2"
    assert captured["limit"] == 3


def test_search_returns_empty_list_when_tos_request_fails(client):
    backend = _backend()

    def fail(**_kwargs):
        raise RuntimeError("service unavailable")

    client.search_context_bucket_memory = fail

    assert backend.search_memory("user-1", "hobbies", 3) == []


def test_long_term_memory_registers_tos_backend(client, monkeypatch):
    monkeypatch.setenv("DATABASE_TOS_CONTEXT_ACCOUNT_ID", "2100000000")
    monkeypatch.setenv(
        "DATABASE_TOS_CONTEXT_CONTROL_ENDPOINT", "tosapi-controller.example.com"
    )

    memory = LongTermMemory(backend="tos_context", app_name="agent-memory")

    assert isinstance(memory._backend, TosContextBucketLTMBackend)
    assert memory._backend.context_bucket_name == "agent-memory"


@pytest.mark.asyncio
async def test_long_term_memory_forwards_tos_save_kwargs(client, monkeypatch):
    monkeypatch.setenv("DATABASE_TOS_CONTEXT_ACCOUNT_ID", "2100000000")
    monkeypatch.setenv(
        "DATABASE_TOS_CONTEXT_CONTROL_ENDPOINT", "tosapi-controller.example.com"
    )
    memory = LongTermMemory(backend="tos_context", app_name="agent-memory")
    monkeypatch.setattr(
        memory, "_filter_and_convert_events", lambda _events, **_kwargs: ["text"]
    )

    await memory.add_session_to_memory(
        SimpleNamespace(id="session-1", user_id="user-1", events=[]),
        infer=False,
        agent_id="agent-1",
    )

    # The backend strips the framework-injected `session_id` / `app_name`
    # kwargs that the TOS SDK does not accept, so they must not appear here.
    assert client.created_memories == [
        {
            "account_id": "2100000000",
            "context_bucket_name": "agent-memory",
            "context_set_name": "user-1",
            "content": "text",
            "infer": False,
            "agent_id": "agent-1",
        }
    ]


def test_uses_explicit_credentials_and_session_token(client):
    _backend(
        volcengine_access_key="env-ak",
        volcengine_secret_key="env-sk",
        session_token="env-sts",
    )

    assert client.init_args[:2] == ("env-ak", "env-sk")
    assert client.init_kwargs["security_token"] == "env-sts"


def test_falls_back_to_vefaas_iam_when_credentials_missing(client):
    # `client` fixture stubs get_credential_from_vefaas_iam -> iam-ak/sk/sts.
    _backend()

    assert client.init_args[:2] == ("iam-ak", "iam-sk")
    assert client.init_kwargs["security_token"] == "iam-sts"


def test_session_token_defaults_to_volcengine_env(client, monkeypatch):
    monkeypatch.setenv("VOLCENGINE_SESSION_TOKEN", "global-sts")
    _backend(
        volcengine_access_key="env-ak",
        volcengine_secret_key="env-sk",
    )

    assert client.init_kwargs["security_token"] == "global-sts"


def test_asserts_when_context_bucket_unsupported(monkeypatch):
    # Simulate an older `tos` SDK: `TosClientV2` exists but lacks the
    # ContextBucket methods. The probe must fail closed with an upgrade hint.
    # Note: this test intentionally does NOT use the `client` fixture, which
    # bypasses the probe.
    class _OldTosClientV2:
        pass

    monkeypatch.setattr(tos_context_bucket_backend, "TosClientV2", _OldTosClientV2)

    with pytest.raises(RuntimeError) as excinfo:
        tos_context_bucket_backend._assert_context_bucket_supported()

    message = str(excinfo.value)
    assert "create_context_bucket_memory" in message
    assert "search_context_bucket_memory" in message
    assert "tos>=2.9.4b1" in message


def test_probe_passes_when_context_bucket_methods_present(monkeypatch):
    class _NewTosClientV2:
        def create_context_bucket_memory(self):  # pragma: no cover - stub
            ...

        def search_context_bucket_memory(self):  # pragma: no cover - stub
            ...

    monkeypatch.setattr(tos_context_bucket_backend, "TosClientV2", _NewTosClientV2)

    # Should not raise.
    tos_context_bucket_backend._assert_context_bucket_supported()
