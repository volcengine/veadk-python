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

import threading

import pytest

from veadk.knowledgebase import KnowledgeBase
from veadk.knowledgebase.backends.base_backend import BaseKnowledgebaseBackend
from veadk.knowledgebase.entry import KnowledgebaseEntry
from veadk.tools import load_knowledgebase_tool as legacy_tool
from veadk.tools.builtin_tools.load_knowledgebase import LoadKnowledgebaseTool


class FakeSyncBackend(BaseKnowledgebaseBackend):
    search_thread_id: int | None = None

    def precheck_index_naming(self) -> None:
        pass

    def add_from_directory(self, directory: str, *args, **kwargs) -> bool:
        return True

    def add_from_files(self, files: list[str], *args, **kwargs) -> bool:
        return True

    def add_from_text(self, text: str | list[str], *args, **kwargs) -> bool:
        return True

    def search(self, query: str, top_k: int = 5) -> list[str]:
        self.search_thread_id = threading.get_ident()
        return [f"generic result for {query}"]


class FakeKnowledgeBase:
    name = "fake_kb"
    backend = "fake"

    def __init__(self):
        self.search_thread_id = None

    def search(self, query: str):
        self.search_thread_id = threading.get_ident()
        return [KnowledgebaseEntry(content=f"result for {query}")]


@pytest.mark.asyncio
async def test_load_knowledgebase_runs_sync_search_in_worker_thread():
    event_loop_thread_id = threading.get_ident()
    knowledgebase = FakeKnowledgeBase()
    tool = LoadKnowledgebaseTool(knowledgebase=knowledgebase)  # type: ignore[arg-type]

    response = await tool.load_knowledgebase("openviking", tool_context=None)  # type: ignore[arg-type]

    assert response.knowledges == [KnowledgebaseEntry(content="result for openviking")]
    assert knowledgebase.search_thread_id is not None
    assert knowledgebase.search_thread_id != event_loop_thread_id


@pytest.mark.asyncio
async def test_legacy_load_knowledgebase_runs_sync_search_in_worker_thread():
    event_loop_thread_id = threading.get_ident()
    knowledgebase = FakeKnowledgeBase()
    original_knowledgebase = legacy_tool.knowledgebase
    original_knowledgebase_cls = legacy_tool.KnowledgeBase
    legacy_tool.knowledgebase = knowledgebase  # type: ignore[assignment]
    legacy_tool.KnowledgeBase = FakeKnowledgeBase  # type: ignore[misc]

    try:
        response = await legacy_tool.search_knowledgebase(None, "legacy", "app")
    finally:
        legacy_tool.knowledgebase = original_knowledgebase
        legacy_tool.KnowledgeBase = original_knowledgebase_cls

    assert response.knowledges == [KnowledgebaseEntry(content="result for legacy")]
    assert knowledgebase.search_thread_id is not None
    assert knowledgebase.search_thread_id != event_loop_thread_id


@pytest.mark.asyncio
async def test_load_knowledgebase_to_thread_works_for_generic_knowledgebase_backend():
    event_loop_thread_id = threading.get_ident()
    backend = FakeSyncBackend(index="generic")
    knowledgebase = KnowledgeBase(backend=backend)
    tool = LoadKnowledgebaseTool(knowledgebase=knowledgebase)

    response = await tool.load_knowledgebase("generic", tool_context=None)  # type: ignore[arg-type]

    assert response.knowledges == [
        KnowledgebaseEntry(content="generic result for generic")
    ]
    assert backend.search_thread_id is not None
    assert backend.search_thread_id != event_loop_thread_id


@pytest.mark.asyncio
async def test_legacy_to_thread_works_for_generic_knowledgebase_backend():
    event_loop_thread_id = threading.get_ident()
    backend = FakeSyncBackend(index="generic")
    knowledgebase = KnowledgeBase(backend=backend)
    original_knowledgebase = legacy_tool.knowledgebase
    legacy_tool.knowledgebase = knowledgebase

    try:
        response = await legacy_tool.search_knowledgebase(None, "legacy", "app")
    finally:
        legacy_tool.knowledgebase = original_knowledgebase

    assert response.knowledges == [
        KnowledgebaseEntry(content="generic result for legacy")
    ]
    assert backend.search_thread_id is not None
    assert backend.search_thread_id != event_loop_thread_id
