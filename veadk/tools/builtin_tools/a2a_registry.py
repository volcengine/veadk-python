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
        reaches a terminal state. When the task is terminal, return the A2A
        task's query result to the user.
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
