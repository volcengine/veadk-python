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
"""Safe smart-search adapters for components mounted on an Agent."""

from __future__ import annotations

import asyncio
from typing import Any


async def search_agent_component(
    agent: object,
    source: str,
    query: str,
    *,
    app_name: str,
    user_id: str,
) -> dict[str, Any]:
    """Search one mounted Agent component and return JSON-safe text results."""
    normalized_query = query.strip()
    if not normalized_query:
        return {"mounted": True, "results": []}
    if source == "knowledge":
        return await _search_knowledgebase(agent, normalized_query)
    if source == "memory":
        return await _search_long_term_memory(
            agent,
            normalized_query,
            app_name=app_name,
            user_id=user_id,
        )
    raise ValueError(f"unsupported Agent search source: {source}")


async def _search_knowledgebase(agent: object, query: str) -> dict[str, Any]:
    knowledgebase = getattr(agent, "knowledgebase", None)
    if knowledgebase is None:
        return {"mounted": False, "results": []}

    entries = await asyncio.to_thread(knowledgebase.search, query)
    results = []
    for entry in entries:
        content = entry if isinstance(entry, str) else getattr(entry, "content", None)
        if isinstance(content, str) and content.strip():
            results.append({"content": content.strip()})
    return {
        "mounted": True,
        "sourceName": _component_name(knowledgebase, "知识库", prefer_index=True),
        "sourceType": _component_backend(knowledgebase),
        "results": results,
    }


async def _search_long_term_memory(
    agent: object,
    query: str,
    *,
    app_name: str,
    user_id: str,
) -> dict[str, Any]:
    memory = getattr(agent, "long_term_memory", None)
    if memory is None:
        return {"mounted": False, "results": []}
    if not user_id:
        raise ValueError("user_id is required for long-term memory search")

    response = await memory.search_memory(
        app_name=app_name,
        user_id=user_id,
        query=query,
    )
    results = []
    for entry in getattr(response, "memories", []) or []:
        content = _memory_content(entry)
        if not content:
            continue
        result: dict[str, Any] = {"content": content}
        author = getattr(entry, "author", None)
        if isinstance(author, str) and author:
            result["author"] = author
        timestamp = getattr(entry, "timestamp", None)
        if isinstance(timestamp, (int, float)):
            result["timestamp"] = timestamp
        results.append(result)
    return {
        "mounted": True,
        "sourceName": _component_name(memory, "长期记忆"),
        "sourceType": _component_backend(memory),
        "results": results,
    }


def _memory_content(entry: object) -> str:
    content = getattr(entry, "content", None)
    parts = getattr(content, "parts", None) or []
    texts = []
    for part in parts:
        text = (
            part.get("text") if isinstance(part, dict) else getattr(part, "text", None)
        )
        if isinstance(text, str) and text.strip():
            texts.append(text.strip())
    return "\n".join(texts)


def _component_name(
    component: object,
    fallback: str,
    *,
    prefer_index: bool = False,
) -> str:
    attributes = ("index", "name") if prefer_index else ("name", "index")
    for attribute in attributes:
        value = getattr(component, attribute, None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return fallback


def _component_backend(component: object) -> str:
    backend = getattr(component, "backend", None)
    if isinstance(backend, str):
        return backend.strip()
    return ""
