# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
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

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any, ClassVar

import pytest

from veadk.knowledgebase import KnowledgeBase
from veadk.knowledgebase.backends.openviking_backend import OpenVikingKnowledgeBackend
from veadk.knowledgebase.entry import KnowledgebaseEntry


class FakeOpenVikingClient:
    def __init__(self) -> None:
        self.add_resource_calls: list[dict[str, Any]] = []
        self.added_texts: list[str] = []
        self.find_calls: list[dict[str, Any]] = []
        self.search_calls: list[dict[str, Any]] = []
        self.read_calls: list[dict[str, Any]] = []
        self.overview_calls: list[str] = []
        self.find_response: Any = {
            "status": "ok",
            "result": {
                "resources": [],
                "memories": [],
                "skills": [],
            },
        }
        self.search_response: Any = self.find_response
        self.read_response = "read body"
        self.overview_response = "overview body"
        self.fail_read = False
        self.fail_overview = False
        self.initialize_calls = 0
        self.close_calls = 0

    def initialize(self):
        self.initialize_calls += 1

    def close(self):
        self.close_calls += 1

    def add_resource(self, **kwargs):
        self.add_resource_calls.append(kwargs)
        path = kwargs.get("path")
        if path and Path(path).is_file():
            self.added_texts.append(Path(path).read_text(encoding="utf-8"))
        return {
            "status": "ok",
            "result": {"root_uri": kwargs.get("to") or kwargs.get("parent")},
        }

    def find(self, **kwargs):
        self.find_calls.append(kwargs)
        return self.find_response

    def search(self, **kwargs):
        self.search_calls.append(kwargs)
        return self.search_response

    def read(self, uri: str, offset: int = 0, limit: int = -1):
        self.read_calls.append({"uri": uri, "offset": offset, "limit": limit})
        if self.fail_read:
            raise RuntimeError("read failed")
        return self.read_response

    def overview(self, uri: str):
        self.overview_calls.append(uri)
        if self.fail_overview:
            raise RuntimeError("overview failed")
        return self.overview_response


class FakeOpenVikingKnowledgeBackend(OpenVikingKnowledgeBackend):
    fake_client: ClassVar[FakeOpenVikingClient | None] = None
    built_clients: ClassVar[list[FakeOpenVikingClient]] = []

    def _build_client(self):
        client = self.fake_client or FakeOpenVikingClient()
        self.built_clients.append(client)
        return client


def make_backend(
    client: FakeOpenVikingClient | None = None,
    default_openviking_user_id: str | None = "owner",
    **kwargs,
) -> FakeOpenVikingKnowledgeBackend:
    FakeOpenVikingKnowledgeBackend.fake_client = client
    FakeOpenVikingKnowledgeBackend.built_clients = []
    if default_openviking_user_id is not None:
        kwargs.setdefault("openviking_user_id", default_openviking_user_id)
    try:
        return FakeOpenVikingKnowledgeBackend(**kwargs)
    finally:
        FakeOpenVikingKnowledgeBackend.fake_client = None


def test_knowledgebase_openviking_instantiates():
    kb = KnowledgeBase(
        backend="openviking",
        app_name="demo",
        backend_config={
            "index": "demo",
            "url": "http://127.0.0.1:1933",
            "api_key": "test-key",
            "openviking_user_id": "owner",
        },
    )

    assert isinstance(kb._backend, OpenVikingKnowledgeBackend)
    assert kb._backend.openviking_user_id == "owner"
    assert kb._backend.target_uri == "viking://user/owner/resources/demo/"


def test_missing_index_and_app_name_keeps_existing_error():
    with pytest.raises(ValueError, match="Either `index` or `app_name`"):
        KnowledgeBase(backend="openviking")


def test_backend_config_requires_its_own_index_even_with_app_name():
    with pytest.raises(Exception, match="index|Field required"):
        KnowledgeBase(
            backend="openviking",
            app_name="demo",
            backend_config={
                "url": "http://127.0.0.1:1933",
                "api_key": "test-key",
                "openviking_user_id": "owner",
            },
        )


def test_default_target_uri_from_openviking_user_id_and_index():
    backend = make_backend(index="demo", openviking_user_id="alice")

    assert backend.openviking_user_id == "alice"
    assert backend.target_uri == "viking://user/alice/resources/demo/"


def test_legacy_user_id_still_sets_default_target_uri():
    backend = make_backend(
        index="demo",
        user_id="legacy_owner",
        default_openviking_user_id=None,
    )

    assert backend.openviking_user_id == "legacy_owner"
    assert backend.user_id == "legacy_owner"
    assert backend.target_uri == "viking://user/legacy_owner/resources/demo/"


def test_explicit_target_uri_is_used_without_openviking_user_id():
    backend = make_backend(
        index="demo",
        target_uri="viking://resources/shared",
        openviking_user_id=None,
    )

    assert backend.target_uri == "viking://resources/shared/"


def test_missing_openviking_user_id_without_target_uri_defaults_to_default(monkeypatch):
    monkeypatch.delenv("DATABASE_OPENVIKING_USER_ID", raising=False)
    monkeypatch.delenv("OPENVIKING_USER_ID", raising=False)
    backend = make_backend(index="demo", default_openviking_user_id=None)

    assert backend.openviking_user_id == "default"
    assert backend.user_id == "default"
    assert backend.target_uri == "viking://user/default/resources/demo/"


def test_default_target_uri_reads_openviking_user_id_from_env(monkeypatch):
    monkeypatch.setenv("DATABASE_OPENVIKING_USER_ID", "env_owner")

    backend = make_backend(index="demo", default_openviking_user_id=None)

    assert backend.openviking_user_id == "env_owner"
    assert backend.target_uri == "viking://user/env_owner/resources/demo/"


def test_openviking_backend_close_releases_client():
    client = FakeOpenVikingClient()
    backend = make_backend(client, index="demo")

    assert client.initialize_calls == 1

    backend.close()

    assert client.close_calls == 1
    assert backend._client is None

    backend.close()

    assert client.close_calls == 1


def test_openviking_backend_reconnects_after_close():
    first_client = FakeOpenVikingClient()
    backend = make_backend(first_client, index="demo")

    backend.close()
    entries = backend.search("policy")

    assert entries == []
    assert first_client.close_calls == 1
    assert len(FakeOpenVikingKnowledgeBackend.built_clients) == 2
    second_client = FakeOpenVikingKnowledgeBackend.built_clients[1]
    assert second_client.initialize_calls == 1
    assert second_client.find_calls[0]["query"] == "policy"
    assert backend._client is second_client


def test_knowledgebase_close_forwards_to_backend():
    client = FakeOpenVikingClient()
    backend = make_backend(client, index="demo")
    kb = KnowledgeBase(backend=backend)

    kb.close()

    assert client.close_calls == 1
    assert backend._client is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("openviking_user_id", "team/a"),
        ("openviking_user_id", "team:alpha"),
        ("openviking_user_id", "team alpha"),
        ("openviking_user_id", "."),
        ("openviking_user_id", ".."),
        ("index", "docs/faq"),
        ("index", "../faq"),
        ("index", "docs:faq"),
        ("index", "docs faq"),
    ],
)
def test_default_target_uri_rejects_unsafe_path_segments(field, value):
    kwargs = {"index": "demo", "openviking_user_id": "owner"}
    kwargs[field] = value

    with pytest.raises(Exception, match="safe single path segment"):
        make_backend(**kwargs)


def test_openviking_backends_load_config_yaml(tmp_path):
    (tmp_path / "config.yaml").write_text(
        """database:
  openviking:
    url: http://config-yaml.example
    api_key: config-key
    user_id: config-owner
""",
        encoding="utf-8",
    )
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    for name in [
        "DATABASE_OPENVIKING_URL",
        "DATABASE_OPENVIKING_API_KEY",
        "DATABASE_OPENVIKING_USER_ID",
        "DATABASE_OPENVIKING_TARGET_URI",
        "OPENVIKING_URL",
        "OPENVIKING_API_KEY",
        "OPENVIKING_USER_ID",
        "OPENVIKING_TARGET_URI",
    ]:
        env.pop(name, None)
    env["PYTHONPATH"] = (
        str(repo_root)
        if not env.get("PYTHONPATH")
        else f"{repo_root}{os.pathsep}{env['PYTHONPATH']}"
    )
    scripts = [
        (
            "knowledgebase",
            """
from veadk.knowledgebase.backends.openviking_backend import OpenVikingKnowledgeBackend


class FakeKnowledgeBackend(OpenVikingKnowledgeBackend):
    def _build_client(self):
        return object()


kb = FakeKnowledgeBackend(index="faq")
assert kb.url == "http://config-yaml.example"
assert kb.api_key == "config-key"
assert kb.openviking_user_id == "config-owner"
assert kb.target_uri == "viking://user/config-owner/resources/faq/"
""",
        ),
        (
            "long_term_memory",
            """
from veadk.memory.long_term_memory_backends.openviking_backend import OpenVikingLTMBackend

ltm = OpenVikingLTMBackend(index="support")
assert ltm.url == "http://config-yaml.example"
assert ltm.api_key == "config-key"
assert ltm.openviking_user_id == "config-owner"
""",
        ),
    ]

    for name, script in scripts:
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=tmp_path,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 0, f"{name} failed: {result.stderr}"


def test_add_from_files_imports_each_file_under_target_uri():
    client = FakeOpenVikingClient()
    backend = make_backend(client, index="demo")

    assert backend.add_from_files(["a.md", "b.md"])

    assert [call["path"] for call in client.add_resource_calls] == ["a.md", "b.md"]
    assert all(
        call["parent"] == "viking://user/owner/resources/demo/"
        for call in client.add_resource_calls
    )
    assert all(call["wait"] is True for call in client.add_resource_calls)
    assert all(call["timeout"] == 300 for call in client.add_resource_calls)


def test_add_from_directory_imports_to_target_uri_with_structure():
    client = FakeOpenVikingClient()
    backend = make_backend(client, index="demo")

    assert backend.add_from_directory("./docs")

    assert client.add_resource_calls == [
        {
            "path": "./docs",
            "to": "viking://user/owner/resources/demo/",
            "wait": True,
            "timeout": 300,
            "strict": False,
            "ignore_dirs": None,
            "include": None,
            "exclude": None,
            "directly_upload_media": True,
            "preserve_structure": True,
            "watch_interval": 0,
            "args": None,
            "telemetry": False,
        }
    ]


def test_add_from_text_writes_temp_files_and_reuses_file_import():
    client = FakeOpenVikingClient()
    backend = make_backend(client, index="demo")

    assert backend.add_from_text(["alpha", "beta"])

    assert len(client.add_resource_calls) == 2
    assert client.added_texts == ["alpha", "beta"]


def test_search_converts_resources_to_entries_without_memories_or_skills():
    client = FakeOpenVikingClient()
    client.find_response = {
        "status": "ok",
        "result": {
            "resources": [
                {
                    "uri": "viking://resources/demo/a.md",
                    "abstract": "resource abstract",
                    "score": 0.9,
                    "match_reason": "semantic",
                    "context_type": "resource",
                    "is_leaf": True,
                }
            ],
            "memories": [{"abstract": "memory abstract"}],
            "skills": [{"abstract": "skill abstract"}],
        },
    }
    backend = make_backend(
        client,
        index="demo",
        hydrate_results=False,
    )

    entries = backend.search("policy", top_k=3)

    assert len(entries) == 1
    assert isinstance(entries[0], KnowledgebaseEntry)
    assert entries[0].content == "resource abstract"
    assert entries[0].metadata == {
        "uri": "viking://resources/demo/a.md",
        "score": 0.9,
        "match_reason": "semantic",
        "context_type": "resource",
        "is_leaf": True,
    }
    assert client.find_calls[0]["target_uri"] == "viking://user/owner/resources/demo/"
    assert client.find_calls[0]["limit"] == 3


def test_hydrate_file_resource_reads_content():
    client = FakeOpenVikingClient()
    client.find_response = {
        "result": {
            "resources": [
                {
                    "uri": "viking://resources/demo/a.md",
                    "abstract": "abstract",
                    "is_leaf": True,
                }
            ]
        }
    }
    backend = make_backend(
        client,
        index="demo",
        hydrate_results=True,
        read_limit=123,
    )

    entries = backend.search("policy")

    assert entries[0].content == "read body"
    assert client.read_calls == [
        {
            "uri": "viking://resources/demo/a.md",
            "offset": 0,
            "limit": 123,
        }
    ]


def test_hydrate_directory_resource_reads_overview():
    client = FakeOpenVikingClient()
    client.find_response = {
        "result": {
            "resources": [
                {
                    "uri": "viking://resources/demo/",
                    "abstract": "abstract",
                    "is_leaf": False,
                }
            ]
        }
    }
    backend = make_backend(
        client,
        index="demo",
        hydrate_results=True,
    )

    entries = backend.search("policy")

    assert entries[0].content == "overview body"
    assert client.overview_calls == ["viking://resources/demo/"]


def test_hydrate_failure_falls_back_to_abstract():
    client = FakeOpenVikingClient()
    client.fail_read = True
    client.find_response = {
        "result": {
            "resources": [
                {
                    "uri": "viking://resources/demo/a.md",
                    "abstract": "fallback abstract",
                    "is_leaf": True,
                }
            ]
        }
    }
    backend = make_backend(client, index="demo")

    entries = backend.search("policy")

    assert entries[0].content == "fallback abstract"


def test_score_threshold_and_context_search_are_forwarded():
    client = FakeOpenVikingClient()
    client.search_response = {
        "result": {
            "resources": [
                {
                    "uri": "viking://resources/demo/a.md",
                    "abstract": "abstract",
                    "is_leaf": True,
                }
            ]
        }
    }
    backend = make_backend(
        client,
        index="demo",
        hydrate_results=False,
        score_threshold=0.3,
        use_context_search=True,
    )

    backend.search("policy", top_k=7, session_id="s1")

    assert client.find_calls == []
    assert client.search_calls[0]["score_threshold"] == 0.3
    assert client.search_calls[0]["limit"] == 7
    assert client.search_calls[0]["session_id"] == "s1"
