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

    def _build_client(self):
        return self.fake_client or FakeOpenVikingClient()


def make_backend(
    client: FakeOpenVikingClient | None = None,
    **kwargs,
) -> FakeOpenVikingKnowledgeBackend:
    FakeOpenVikingKnowledgeBackend.fake_client = client
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
        },
    )

    assert isinstance(kb._backend, OpenVikingKnowledgeBackend)
    assert kb._backend.target_uri == "viking://resources/demo/"


def test_missing_index_and_app_name_keeps_existing_error():
    with pytest.raises(ValueError, match="Either `index` or `app_name`"):
        KnowledgeBase(backend="openviking")


def test_default_target_uri_from_index():
    backend = make_backend(index="demo")

    assert backend.target_uri == "viking://resources/demo/"


def test_add_from_files_imports_each_file_under_target_uri():
    client = FakeOpenVikingClient()
    backend = make_backend(client, index="demo")

    assert backend.add_from_files(["a.md", "b.md"])

    assert [call["path"] for call in client.add_resource_calls] == ["a.md", "b.md"]
    assert all(
        call["parent"] == "viking://resources/demo/"
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
            "to": "viking://resources/demo/",
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
    assert client.find_calls[0]["target_uri"] == "viking://resources/demo/"
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
