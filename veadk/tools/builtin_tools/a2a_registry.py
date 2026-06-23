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

import re
from collections.abc import Callable
from typing import Any

from veadk.a2a.registry_client import (
    AgentKitA2ARegistryConfig,
    RegistryError,
    create_task,
    failure,
    poll_task,
    registry_config_from_env,
    search_agent_cards,
)
from veadk.utils.logger import get_logger

logger = get_logger(__name__)


def build_a2a_registry_tools(
    config: AgentKitA2ARegistryConfig | None = None,
) -> list[Callable[..., dict[str, Any]]]:
    """Build the three AgentKit A2A registry tools for a harness agent."""

    resolved_config = config or registry_config_from_env()

    def a2a_registry_search_agent_cards(prompt: str = "") -> dict[str, Any]:
        """Search the AgentKit A2A registry for remote agents that can handle a task.

        Use this first when you determine that a remote A2A Agent may be needed
        for the task, such as when specialist capabilities, delegation, or agent
        discovery could improve the result. Pass a concise search prompt, not
        the complete user request. If the user's request is long, summarize it
        into keywords or a short task description before calling this tool.
        The UTF-8 encoded `prompt` must not exceed 2048 bytes. Inspect the
        returned `agents` list, compare each agent's `name`, `description`, and
        `skills`, then choose the best `agent_name` for
        `a2a_registry_task_create` if a suitable agent is available.
        """

        try:
            return search_agent_cards(prompt, None, resolved_config)
        except RegistryError as exc:
            return failure(exc.code, exc.message, exc.diagnostics)
        except Exception as exc:  # noqa: BLE001 - tool calls should return safely.
            return failure("INTERNAL_ERROR", str(exc))

    def a2a_registry_task_create(
        agent_name: str, input: str, task_id: str | None = None
    ) -> dict[str, Any]:
        """Send the user's task to the selected remote A2A agent.

        Use this after `a2a_registry_search_agent_cards` and pass the exact
        selected `agents[].name` as `agent_name`. Put the full user request in
        `input`. This calls the remote agent with A2A `message/send` and may
        return either a final `response.text` or a `task.id`. If it returns a
        `task.id` without a final response, call `a2a_registry_task_poll` with
        the same `agent_name` and `task_id`.
        """

        try:
            return create_task(agent_name, input, task_id, resolved_config)
        except RegistryError as exc:
            return failure(exc.code, exc.message, exc.diagnostics)
        except Exception as exc:  # noqa: BLE001
            return failure("INTERNAL_ERROR", str(exc))

    def a2a_registry_task_poll(
        agent_name: str, task_id: str, history_length: int = 10
    ) -> dict[str, Any]:
        """Check the status of an existing remote A2A task.

        Use this after `a2a_registry_task_create` returns a `task.id` without a
        final response. This tool calls A2A `tasks/get` once with the same
        `agent_name` and `task_id`. If `is_terminal` is false, do not create a
        new task; call this tool again with the same `task_id` until the task
        reaches a terminal state such as `completed`, `failed`, `canceled`, or
        `rejected`. When the task is terminal, return the A2A task's query
        result to the user.
        """

        try:
            return poll_task(agent_name, task_id, history_length, resolved_config)
        except RegistryError as exc:
            return failure(exc.code, exc.message, exc.diagnostics)
        except Exception as exc:  # noqa: BLE001
            return failure("INTERNAL_ERROR", str(exc))

    return [
        a2a_registry_search_agent_cards,
        a2a_registry_task_create,
        a2a_registry_task_poll,
    ]


def build_remote_a2a_agent_tools(
    prompt: str,
    config: AgentKitA2ARegistryConfig | None = None,
) -> list[Callable[..., dict[str, Any]]]:
    """Build one-turn remote A2A agent tools from a registry semantic search."""

    resolved_config = config or registry_config_from_env()
    try:
        search_result = search_agent_cards(
            prompt,
            None,
            resolved_config,
            strip_prompt=False,
        )
    except RegistryError as exc:
        logger.warning(f"Skipping dynamic A2A agent tools: {exc.code}: {exc.message}")
        return []

    agents = search_result.get("agents") or []
    tools: list[Callable[..., dict[str, Any]]] = []
    seen_agent_names: set[str] = set()
    seen_tool_names: set[str] = set()
    for index, agent in enumerate(agents):
        agent_name = agent.get("name") if isinstance(agent, dict) else ""
        if not agent_name or agent_name in seen_agent_names:
            continue
        seen_agent_names.add(agent_name)

        tool_name = _unique_remote_a2a_tool_name(agent_name, index, seen_tool_names)
        tools.append(
            _make_remote_a2a_agent_tool(
                tool_name=tool_name,
                agent=agent,
                config=resolved_config,
            )
        )

    return tools


def _unique_remote_a2a_tool_name(
    agent_name: str, index: int, seen_names: set[str]
) -> str:
    normalized = re.sub(r"[^0-9A-Za-z_]+", "_", agent_name).strip("_").lower()
    if not normalized:
        normalized = f"agent_{index + 1}"
    if normalized[0].isdigit():
        normalized = f"agent_{normalized}"

    base_name = f"remote_a2a_{normalized}"
    name = base_name
    suffix = 2
    while name in seen_names:
        name = f"{base_name}_{suffix}"
        suffix += 1
    seen_names.add(name)
    return name


def _make_remote_a2a_agent_tool(
    *,
    tool_name: str,
    agent: dict[str, Any],
    config: AgentKitA2ARegistryConfig,
) -> Callable[..., dict[str, Any]]:
    agent_name = agent.get("name") or tool_name
    agent_description = agent.get("description") or ""
    skill_descriptions = "; ".join(
        skill.get("description", "")
        for skill in agent.get("skills", [])
        if isinstance(skill, dict) and skill.get("description")
    )

    def remote_a2a_agent_tool(input: str, task_id: str | None = None) -> dict[str, Any]:
        try:
            if not input or not input.strip():
                return failure("INVALID_ARGUMENT", "input is required")

            return create_task(agent_name, input, task_id, config)
        except RegistryError as exc:
            return failure(exc.code, exc.message, exc.diagnostics)
        except Exception as exc:  # noqa: BLE001
            return failure("INTERNAL_ERROR", str(exc))

    remote_a2a_agent_tool.__name__ = tool_name
    remote_a2a_agent_tool.__qualname__ = tool_name
    remote_a2a_agent_tool.__doc__ = (
        f"Remote A2A agent `{agent_name}`. "
        f"{agent_description or 'Use this tool when the request matches this remote agent.'} "
        f"Skills: {skill_descriptions or 'No skills listed.'} "
        "Put the full user request in `input`. If continuing an existing remote "
        "task, pass its `task_id`; otherwise leave `task_id` empty. The tool "
        "returns either `response.text` or a remote `task.id`. If it returns a "
        f"`task.id` without `response.text`, call `a2a_registry_task_poll` with "
        f"`agent_name` set to `{agent_name}` and the returned `task_id` until "
        "the task reaches a terminal state."
    )
    return remote_a2a_agent_tool
