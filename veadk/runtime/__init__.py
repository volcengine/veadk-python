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

"""Pluggable agent runtimes for VeADK.

``Agent(runtime=...)`` selects which runtime drives the inner agent loop:

- ``"adk"`` (default): Google ADK's built-in ``BaseLlmFlow`` (handled directly in
  :class:`veadk.agent.Agent`, no runtime object).
- ``"codex"``: the OpenAI Codex SDK as the agent harness.
- ``"piagent"``: a local Pi coding agent binary as the agent harness.
"""

from __future__ import annotations

from functools import lru_cache

from veadk.runtime.base_runtime import BaseRuntime


@lru_cache(maxsize=None)
def get_runtime(name: str) -> BaseRuntime:
    """Return the (cached) runtime instance for ``name``.

    Args:
        name (str): Runtime identifier from ``Agent(runtime=...)``. ``"adk"`` is
            handled inline by the agent and never reaches this function.

    Returns:
        BaseRuntime: The runtime instance.

    Raises:
        NotImplementedError: If ``name`` is a known-but-unimplemented runtime.
        ValueError: If ``name`` is unknown.
    """
    if name == "codex":
        try:
            from veadk.runtime.codex import CodexRuntime
        except ModuleNotFoundError as e:
            raise ImportError(
                f"The 'codex' runtime requires extra dependencies (missing: {e.name}). "
                "Install them with: pip install openai-codex fastapi uvicorn "
                "(openai-codex bundles the Codex binary via openai-codex-cli-bin)."
            ) from e

        return CodexRuntime()

    if name == "piagent":
        from veadk.runtime.piagent import PiAgentRuntime

        return PiAgentRuntime()

    raise ValueError(f"Unknown runtime: {name!r}")


__all__ = ["BaseRuntime", "get_runtime"]
