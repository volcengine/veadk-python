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

"""Execution adapter for dynamically constructed ADK roots."""

from __future__ import annotations

import inspect
from collections.abc import Sequence
from typing import Any
from uuid import uuid4

from google.adk.agents import BaseAgent


async def default_executor(root: Any, task: str, name: str) -> str:
    """Execute either a classic BaseAgent or an ADK 2.x workflow node."""
    from google.adk.runners import InMemoryRunner

    if isinstance(root, BaseAgent):
        runner = InMemoryRunner(agent=root, app_name=f"dynamic_{name}")
    else:
        runner = InMemoryRunner(node=root, app_name=f"dynamic_{name}")
    try:
        if hasattr(runner, "run_debug"):
            events = await runner.run_debug(
                task,
                user_id="create_agent",
                session_id=f"run_{uuid4().hex}",
                quiet=True,
            )
        else:  # pragma: no cover - compatibility path for older ADK releases.
            from google.genai import types

            session_id = f"run_{uuid4().hex}"
            await runner.session_service.create_session(
                app_name=runner.app_name,
                user_id="create_agent",
                session_id=session_id,
            )
            events = [
                event
                async for event in runner.run_async(
                    user_id="create_agent",
                    session_id=session_id,
                    new_message=types.UserContent(parts=[types.Part(text=task)]),
                )
            ]
        return _last_text(events)
    finally:
        close = getattr(runner, "close", None)
        if callable(close):
            result = close()
            if inspect.isawaitable(result):
                await result


def _last_text(events: Sequence[Any]) -> str:
    for event in reversed(events):
        content = getattr(event, "content", None)
        parts = getattr(content, "parts", None) or []
        texts = [getattr(part, "text", "") or "" for part in parts]
        text = "".join(texts).strip()
        if text:
            return text
    return ""
