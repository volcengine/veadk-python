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

import json

from veadk.cli.runtime_update_recovery import (
    assess_runtime_update_agent,
    mcp_auth_environment_keys,
    sanitize_runtime_agent_info,
    sanitize_runtime_environment,
)


def test_runtime_environment_exposes_only_allowlisted_public_values() -> None:
    view = sanitize_runtime_environment(
        [
            ("MODEL_AGENT_NAME", "published-model"),
            ("MODEL_AGENT_PROVIDER", "openai"),
            ("MODEL_AGENT_API_BASE", "https://model.example.com/v1"),
            ("MODEL_AGENT_API_KEY_ID", "key-id"),
            ("MODEL_AGENT_API_KEY_NAME", "key-name"),
            ("MODEL_AGENT_API_KEY", "model-secret"),
            ("MCP_API_KEY", "mcp-secret"),
            (
                "MCP_SERVERS_JSON",
                '[{"headers":{"Authorization":"Bearer embedded-secret"}}]',
            ),
            ("CUSTOM_TOKEN", "custom-secret"),
            ("ARBITRARY_PUBLIC_LOOKING_VALUE", "must-not-reach-browser"),
        ]
    )

    assert view.public_envs == (
        {"key": "MODEL_AGENT_NAME", "value": "published-model"},
        {"key": "MODEL_AGENT_PROVIDER", "value": "openai"},
        {
            "key": "MODEL_AGENT_API_BASE",
            "value": "https://model.example.com/v1",
        },
        {"key": "MODEL_AGENT_API_KEY_ID", "value": "key-id"},
        {"key": "MODEL_AGENT_API_KEY_NAME", "value": "key-name"},
    )
    assert set(view.configured_env_keys) == {
        "MODEL_AGENT_API_KEY",
        "MCP_API_KEY",
        "MCP_SERVERS_JSON",
        "CUSTOM_TOKEN",
        "ARBITRARY_PUBLIC_LOOKING_VALUE",
    }
    serialized = json.dumps(view.as_payload())
    for protected in (
        "model-secret",
        "mcp-secret",
        "embedded-secret",
        "custom-secret",
        "must-not-reach-browser",
    ):
        assert protected not in serialized


def test_runtime_environment_rejects_credential_bearing_public_url() -> None:
    credential_bearing_url = (
        "https://"
        + "fixture-user"
        + ":"
        + "fixture-password"
        + "@model.example.com/v1?token="
        + "fixture-token"
    )
    view = sanitize_runtime_environment(
        [
            (
                "MODEL_AGENT_API_BASE",
                credential_bearing_url,
            )
        ]
    )

    assert view.public_envs == ()
    assert view.configured_env_keys == ("MODEL_AGENT_API_BASE",)
    assert "password" not in json.dumps(view.as_payload())


def test_mcp_auth_environment_keys_walks_the_complete_agent_tree() -> None:
    keys = mcp_auth_environment_keys(
        {
            "mcpTools": [
                {"authTokenEnv": "MCP_ROOT_TOKEN"},
                {"authTokenEnv": "MCP_SHARED_TOKEN"},
                {"authTokenEnv": "not-valid-name"},
                {"authTokenEnv": ""},
            ],
            "subAgents": [
                {
                    "mcpTools": [
                        {"authTokenEnv": "MCP_CHILD_TOKEN"},
                        {"authTokenEnv": "MCP_SHARED_TOKEN"},
                    ],
                    "subAgents": [],
                }
            ],
            "workflow": {
                "nodes": [
                    {
                        "agent": {
                            "mcpTools": [
                                {"authTokenEnv": "MCP_WORKFLOW_TOKEN"},
                                {"authTokenEnv": 123},
                            ],
                            "subAgents": [],
                        }
                    },
                    {"agent": "invalid"},
                ]
            },
        }
    )

    assert keys == (
        "MCP_ROOT_TOKEN",
        "MCP_SHARED_TOKEN",
        "MCP_CHILD_TOKEN",
        "MCP_WORKFLOW_TOKEN",
    )


def test_runtime_agent_info_keeps_only_read_only_introspection_fields() -> None:
    sanitized = sanitize_runtime_agent_info(
        {
            "name": "published-agent",
            "description": "Published description",
            "tools": ["SkillToolset"],
            "skills": [
                {
                    "name": "ops-skill",
                    "description": "Operational checks",
                    "authToken": "skill-secret",
                }
            ],
            "components": [
                {
                    "kind": "toolset",
                    "name": "MCP",
                    "description": "Mounted toolset",
                    "headers": {"Authorization": "component-secret"},
                }
            ],
            "searchSources": ["knowledge", "private-secret-source"],
            "graph": {
                "id": "root",
                "name": "published-agent",
                "type": "llm",
                "tools": ["SkillToolset"],
                "skills": [{"name": "ops-skill", "token": "graph-secret"}],
                "credential": "graph-root-secret",
                "children": [],
            },
            "runtimeSecret": "must-not-reach-browser",
            "environment": {"MCP_API_KEY": "embedded-secret"},
        }
    )

    assert sanitized == {
        "name": "published-agent",
        "description": "Published description",
        "tools": ["SkillToolset"],
        "skills": [{"name": "ops-skill", "description": "Operational checks"}],
        "components": [
            {
                "kind": "toolset",
                "name": "MCP",
                "description": "Mounted toolset",
            }
        ],
        "searchSources": ["knowledge"],
        "graph": {
            "id": "root",
            "name": "published-agent",
            "type": "llm",
            "tools": ["SkillToolset"],
            "skills": [{"name": "ops-skill"}],
            "children": [],
        },
    }
    serialized = json.dumps(sanitized)
    for protected in (
        "must-not-reach-browser",
        "embedded-secret",
        "skill-secret",
        "component-secret",
        "graph-secret",
        "graph-root-secret",
        "private-secret-source",
    ):
        assert protected not in serialized


def test_workflow_snapshot_drops_unrecognized_fields_before_returning_to_browser() -> (
    None
):
    recovery = assess_runtime_update_agent(
        agent_info={
            "name": "workflow-agent",
            "draft": {
                "name": "workflow-agent",
                "workflow": {
                    "type": "sequential",
                    "credential": "workflow-secret",
                    "nodes": [
                        {
                            "id": "worker",
                            "credential": "node-secret",
                            "agent": {"name": "worker"},
                        }
                    ],
                    "edges": [
                        {
                            "from": "worker",
                            "to": "worker",
                            "credential": "edge-secret",
                        }
                    ],
                },
            },
        },
        fallback_draft=None,
        fallback_available=False,
        runtime_id="runtime-workflow",
        current_version=1,
    )

    assert recovery.can_update is True
    serialized = json.dumps(recovery.as_payload())
    assert "workflow-secret" not in serialized
    assert "node-secret" not in serialized
    assert "edge-secret" not in serialized


def test_agent_info_draft_is_sanitized_and_accepted_for_regeneration() -> None:
    recovery = assess_runtime_update_agent(
        agent_info={
            "name": "published-agent",
            "draft": {
                "name": "published-agent",
                "description": "Published description",
                "mcpTools": [
                    {
                        "name": "orders",
                        "transport": "http",
                        "url": "https://mcp.example.com/mcp",
                        "authTokenEnv": "MCP_ORDERS_TOKEN",
                    }
                ],
                "deployment": {
                    "feishuEnabled": False,
                    "envValues": {
                        "MCP_ORDERS_TOKEN": "old-secret",
                        "MODEL_AGENT_PROVIDER": "openai",
                    },
                },
            },
        },
        fallback_draft=None,
        fallback_available=False,
        runtime_id="runtime-1",
        current_version=7,
    )

    assert recovery.can_update is True
    assert recovery.status == "draft-only"
    assert recovery.edit_mode == "regenerate"
    assert recovery.source == "agent-info"
    assert recovery.reason_code == ""
    assert recovery.etag
    assert recovery.agent["draft"]["mcpTools"][0]["authTokenEnv"] == (
        "MCP_ORDERS_TOKEN"
    )
    assert recovery.agent["draft"]["deployment"]["envValues"] == {
        "MODEL_AGENT_PROVIDER": "openai"
    }
    assert "old-secret" not in json.dumps(recovery.as_payload())


def test_agent_draft_fallback_is_used_when_agent_info_has_no_draft() -> None:
    recovery = assess_runtime_update_agent(
        agent_info={"name": "published-agent", "tools": ["tool-a"]},
        fallback_draft={
            "name": "published-agent",
            "description": "Recovered from compatibility endpoint",
            "selectedSkills": [
                {
                    "source": "local",
                    "name": "ops-skill",
                    "folder": "ops-skill",
                    "localFiles": [{"path": "SKILL.md", "content": "# Ops skill\n"}],
                }
            ],
        },
        fallback_available=True,
        runtime_id="runtime-1",
        current_version=7,
    )

    assert recovery.can_update is True
    assert recovery.status == "draft-only"
    assert recovery.source == "agent-draft"
    assert recovery.agent["draft"]["selectedSkills"][0]["name"] == "ops-skill"


def test_available_but_invalid_agent_draft_fallback_is_incompatible() -> None:
    recovery = assess_runtime_update_agent(
        agent_info={"name": "published-agent", "tools": ["SkillToolset"]},
        fallback_draft=None,
        fallback_available=True,
        runtime_id="runtime-1",
        current_version=7,
    )

    assert recovery.can_update is False
    assert recovery.status == "incompatible"
    assert recovery.source == "agent-draft"
    assert recovery.reason_code == "runtime_editable_snapshot_incompatible"


def test_introspection_only_runtime_is_blocked_instead_of_building_empty_lists() -> (
    None
):
    recovery = assess_runtime_update_agent(
        agent_info={
            "name": "custom-agent",
            "tools": ["ResilientMcpToolset"],
            "skills": [{"name": "db-troubleshooter"}],
        },
        fallback_draft=None,
        fallback_available=False,
        runtime_id="runtime-custom",
        current_version=4,
    )

    assert recovery.can_update is False
    assert recovery.status == "introspection-only"
    assert recovery.edit_mode == "blocked"
    assert recovery.source == "none"
    assert recovery.reason_code == "runtime_editable_snapshot_missing"
    assert "原发布配置不可恢复" in recovery.reason
    assert "draft" not in recovery.agent


def test_invalid_or_plaintext_secret_draft_is_incompatible_and_never_echoed() -> None:
    recovery = assess_runtime_update_agent(
        agent_info={
            "name": "unsafe-agent",
            "draft": {
                "name": "unsafe-agent",
                "mcpTools": [
                    {
                        "name": "unsafe",
                        "transport": "http",
                        "url": "https://mcp.example.com/mcp",
                        "authToken": "plaintext-secret",
                    }
                ],
            },
        },
        fallback_draft=None,
        fallback_available=False,
        runtime_id="runtime-unsafe",
        current_version=1,
    )

    assert recovery.can_update is False
    assert recovery.status == "incompatible"
    assert recovery.reason_code == "runtime_editable_snapshot_incompatible"
    assert "draft" not in recovery.agent
    assert "plaintext-secret" not in json.dumps(recovery.as_payload())


def test_invalid_mcp_environment_reference_is_blocked_instead_of_silently_lost() -> (
    None
):
    recovery = assess_runtime_update_agent(
        agent_info={
            "name": "unsafe-agent",
            "draft": {
                "name": "unsafe-agent",
                "mcpTools": [
                    {
                        "name": "orders",
                        "transport": "http",
                        "url": "https://mcp.example.com/mcp",
                        "authTokenEnv": "not-a-valid-env-name",
                    }
                ],
            },
        },
        fallback_draft=None,
        fallback_available=False,
        runtime_id="runtime-unsafe",
        current_version=1,
    )

    assert recovery.can_update is False
    assert recovery.status == "incompatible"
    assert recovery.reason_code == "runtime_editable_snapshot_incompatible"
    assert "draft" not in recovery.agent


def test_excessively_deep_editable_graph_is_blocked_without_recursion_failure() -> None:
    root: dict[str, object] = {"name": "root", "subAgents": []}
    current = root
    for index in range(32):
        child: dict[str, object] = {
            "name": f"child-{index}",
            "subAgents": [],
        }
        current["subAgents"] = [child]
        current = child

    recovery = assess_runtime_update_agent(
        agent_info={"name": "unsafe-agent", "draft": root},
        fallback_draft=None,
        fallback_available=False,
        runtime_id="runtime-deep",
        current_version=1,
    )

    assert recovery.can_update is False
    assert recovery.status == "incompatible"
    assert recovery.reason_code == "runtime_editable_snapshot_incompatible"
    assert "draft" not in recovery.agent
