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

"""Convert a layered ``harness.yaml`` into the env vars the runtime reads.

``harness.yaml`` keeps each component self-contained — a component's backend
``type`` and its connection params live together, which is the most readable
layout for users::

    long_term_memory:
      type: viking
      project: my-project
      region: cn-beijing

Two kinds of fields are converted differently:

* **Everything except the component sections** (``harness_name``, ``model``,
  ``tools``, ``skills``, ``system_prompt``, ``runtime``, ``registry``) is
  flattened with VeADK's own :func:`veadk.utils.misc.flatten_dict` (the flattener
  ``set_envs`` uses for ``config.yaml``): nested keys joined with ``_``, then
  upper-cased, lists comma-joined. So ``model: {name: x}`` -> ``MODEL_NAME``,
  ``tools: [a, b]`` -> ``TOOLS``.
* **Component sections** (``knowledgebase`` / ``long_term_memory`` /
  ``short_term_memory``): ``type`` becomes the harness selector env, and the
  remaining connection params are mapped to the VeADK env vars the backend
  actually reads via :data:`BACKEND_ENV` — these can't be derived by a generic
  flatten (a Viking memory's ``project`` must become ``DATABASE_VIKING_PROJECT``,
  read by :class:`veadk.configs.database_configs.VikingKnowledgebaseConfig`, not
  ``LONG_TERM_MEMORY_PROJECT``).

Note: VeADK keeps one ``DATABASE_<BACKEND>_*`` config per backend, so two
components using the same backend share those vars (e.g. a Viking knowledge base
and a Viking long-term memory).
"""

import json
from typing import Any

from veadk.utils.misc import flatten_dict

# Component section -> the harness selector env naming its backend ``type``
# (read by :func:`veadk.cloud.harness_app.utils.config_from_env`).
COMPONENT_TYPE_ENV: dict[str, str] = {
    "knowledgebase": "KNOWLEDGEBASE_TYPE",
    "long_term_memory": "LONG_TERM_MEMORY_TYPE",
    "short_term_memory": "SHORT_TERM_MEMORY_TYPE",
}

COMPONENT_ID_ENV: dict[str, str] = {
    "knowledgebase": "KNOWLEDGEBASE_ID",
    "long_term_memory": "LONG_TERM_MEMORY_ID",
}

COMPONENT_CONFIG_ENV: dict[str, str] = {
    "knowledgebase": "KNOWLEDGEBASE_CONFIG_JSON",
    "long_term_memory": "LONG_TERM_MEMORY_CONFIG_JSON",
}

COMPONENT_ALIASES: dict[str, tuple[str, ...]] = {
    "knowledgebase": ("konwledgebase",),
    "long_term_memory": ("longterm_memory",),
}

HARNESS_ROOT_KEY = "harness"

MODEL_ENV_ALIASES: dict[str, tuple[str, ...]] = {
    "model_name": ("MODEL_AGENT_NAME", "MODEL_NAME"),
    "temperature": ("MODEL_AGENT_TEMPERATURE",),
    "top_p": ("MODEL_AGENT_TOP_P",),
    "max_llm_calls": ("MAX_LLM_CALLS",),
}

TOOL_CONFIG_ENV: dict[str, dict[str, str]] = {
    "run_code": {
        "tool_id": "AGENTKIT_TOOL_ID_SCRIPT",
        "region": "AGENTKIT_TOOL_REGION",
    },
    "coding": {
        "tool_id": "AGENTKIT_TOOL_ID_OPENCODE",
        "region": "AGENTKIT_TOOL_REGION",
    },
    "mcp_router": {
        "id": "MCP_ROUTER_ID",
        "_id": "MCP_ROUTER_ID",
        "mcp_router_id": "MCP_ROUTER_ID",
        "mcp_toolset_id": "MCP_ROUTER_ID",
        "url": "TOOL_MCP_ROUTER_URL",
        "api_key": "TOOL_MCP_ROUTER_API_KEY",
        "apikey": "TOOL_MCP_ROUTER_API_KEY",
    },
}

# Backend ``type`` -> {harness connection param: VeADK env var}. Mirrors the
# pydantic-settings env prefixes in :mod:`veadk.configs.database_configs`;
# credentials map to the shared top-level ``VOLCENGINE_*`` vars. Backends with no
# connection params map to an empty dict (so a stray param fast-fails as a typo).
BACKEND_ENV: dict[str, dict[str, str]] = {
    "viking": {
        "project": "DATABASE_VIKING_PROJECT",
        "region": "DATABASE_VIKING_REGION",
        "resource_id": "DATABASE_VIKING_RESOURCE_ID",
        "access_key": "VOLCENGINE_ACCESS_KEY",
        "secret_key": "VOLCENGINE_SECRET_KEY",
    },
    "redis": {
        "host": "DATABASE_REDIS_HOST",
        "port": "DATABASE_REDIS_PORT",
        "username": "DATABASE_REDIS_USERNAME",
        "password": "DATABASE_REDIS_PASSWORD",
        "db": "DATABASE_REDIS_DB",
    },
    "opensearch": {
        "host": "DATABASE_OPENSEARCH_HOST",
        "port": "DATABASE_OPENSEARCH_PORT",
        "username": "DATABASE_OPENSEARCH_USERNAME",
        "password": "DATABASE_OPENSEARCH_PASSWORD",
        "use_ssl": "DATABASE_OPENSEARCH_USE_SSL",
        "cert_path": "DATABASE_OPENSEARCH_CERT_PATH",
        "secret_token": "DATABASE_OPENSEARCH_SECRET_TOKEN",
    },
    "mysql": {
        "host": "DATABASE_MYSQL_HOST",
        "user": "DATABASE_MYSQL_USER",
        "password": "DATABASE_MYSQL_PASSWORD",
        "database": "DATABASE_MYSQL_DATABASE",
        "charset": "DATABASE_MYSQL_CHARSET",
    },
    "postgresql": {
        "host": "DATABASE_POSTGRESQL_HOST",
        "port": "DATABASE_POSTGRESQL_PORT",
        "user": "DATABASE_POSTGRESQL_USER",
        "password": "DATABASE_POSTGRESQL_PASSWORD",
        "database": "DATABASE_POSTGRESQL_DATABASE",
    },
    "mem0": {
        "api_key": "DATABASE_MEM0_API_KEY",
        "api_key_id": "DATABASE_MEM0_API_KEY_ID",
        "project_id": "DATABASE_MEM0_PROJECT_ID",
        "base_url": "DATABASE_MEM0_BASE_URL",
    },
    # In-memory / file backends take no connection params.
    "local": {},
    "sqlite": {},
}


# Backends each component supports (drives the `veadk harness add` connection
# flags and lets a component offer only its relevant params). Backends with no
# connection params (local / sqlite / tos_vector / context_search) are omitted.
COMPONENT_BACKENDS: dict[str, list[str]] = {
    "knowledgebase": ["viking", "opensearch", "redis"],
    "long_term_memory": ["viking", "opensearch", "redis", "mem0"],
    "short_term_memory": ["mysql", "postgresql"],
}

# Credentials come from the shared top-level VOLCENGINE_* vars (the deploy `.env`),
# not from per-component CLI flags.
_CREDENTIAL_PARAMS = frozenset({"access_key", "secret_key"})


def component_connection_params(component: str) -> list[str]:
    """Ordered, de-duplicated connection-param names a component's backends accept.

    Used by ``veadk harness add`` to generate one explicit flag per param
    (e.g. ``--long-term-memory-project``). Credential params are excluded.
    """
    params: dict[str, None] = {}
    for backend in COMPONENT_BACKENDS.get(component, []):
        for param in BACKEND_ENV.get(backend, {}):
            if param not in _CREDENTIAL_PARAMS:
                params.setdefault(param, None)
    return list(params)


def _is_empty(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


def _stringify(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple)):
        return ",".join(str(item).strip() for item in value if str(item).strip())
    return str(value)


def to_runtime_env(spec: dict[str, Any]) -> dict[str, str]:
    """Convert a parsed ``harness.yaml`` into the VeADK runtime env var dict.

    Empty values are skipped (VeADK falls back to its own defaults). An unknown
    backend ``type`` raises ``ValueError``. Backend-specific params are also
    exported as ``DATABASE_*`` env vars when supported; the full component config
    is preserved as JSON for resource-level runtime construction.
    """
    spec = _runtime_spec(spec)
    env: dict[str, str] = {}

    # Non-component fields: reuse VeADK's flatten_dict (same as config.yaml).
    # The `auth` block is excluded too: it configures the runtime's gateway
    # authorizer at deploy time (custom_jwt), not the container environment.
    structured_json_fields = {
        "mcp": "MCP_SERVERS_JSON",
        "selected_skills": "SELECTED_SKILLS_JSON",
    }
    special_fields = {
        "builtin_tools",
        "mcp_router_id",
        "mcp_toolset_id",
        "model",
        *MODEL_ENV_ALIASES,
    }
    rest = {
        k: v
        for k, v in spec.items()
        if k not in COMPONENT_TYPE_ENV
        and k not in _component_aliases()
        and k not in structured_json_fields
        and k not in special_fields
        and k != "auth"
    }
    for key, value in flatten_dict(rest).items():
        if _is_empty(value):
            continue
        env[key.upper()] = _stringify(value)
    _add_model_envs(env, spec)
    _add_builtin_tool_envs(env, spec.get("builtin_tools"))
    _add_mcp_router_envs(env, spec)
    for key, env_name in structured_json_fields.items():
        value = spec.get(key)
        if not _is_empty(value):
            env[env_name] = json.dumps(value, ensure_ascii=False)

    _add_harness_enhance_aliases(env, spec)

    # Component sections: `type` selector + backend-specific connection params.
    for component, type_env in COMPONENT_TYPE_ENV.items():
        section: dict[str, Any] = _component_section(spec, component)
        if _is_empty(section.get("type")):
            continue
        backend = str(section["type"])
        env[type_env] = backend

        params = BACKEND_ENV.get(backend)
        if params is None:
            raise ValueError(
                f"Unknown backend type '{backend}' for '{component}'. "
                f"Known: {sorted(BACKEND_ENV)}"
            )
        resource_config = _component_resource_config(section)
        config_env = COMPONENT_CONFIG_ENV.get(component)
        if config_env and resource_config:
            env[config_env] = json.dumps(resource_config, ensure_ascii=False)

        for param, value in section.items():
            if param == "type" or _is_empty(value):
                continue
            if param in {"id", "_id"}:
                id_env = COMPONENT_ID_ENV.get(component)
                if id_env is None:
                    raise ValueError(
                        f"Param '{param}' is not supported for {component}."
                    )
                env[id_env] = _stringify(value)
                continue
            env_name = params.get(param)
            if env_name is None:
                continue
            env[env_name] = _stringify(value)

    return env


def _runtime_spec(spec: dict[str, Any]) -> dict[str, Any]:
    harness_section = spec.get(HARNESS_ROOT_KEY)
    if not isinstance(harness_section, dict):
        return spec
    outer = {k: v for k, v in spec.items() if k != HARNESS_ROOT_KEY}
    return {**outer, **harness_section}


def _add_model_envs(env: dict[str, str], spec: dict[str, Any]) -> None:
    model_section = spec.get("model")
    if isinstance(model_section, dict) and not _is_empty(model_section.get("name")):
        _set_env_aliases(env, MODEL_ENV_ALIASES["model_name"], model_section["name"])
    for key, env_names in MODEL_ENV_ALIASES.items():
        value = spec.get(key)
        if not _is_empty(value):
            _set_env_aliases(env, env_names, value)


def _set_env_aliases(
    env: dict[str, str],
    env_names: tuple[str, ...],
    value: Any,
) -> None:
    string_value = _stringify(value)
    for env_name in env_names:
        env[env_name] = string_value


def _add_builtin_tool_envs(env: dict[str, str], value: Any) -> None:
    entries = _builtin_tool_entries(value)
    if not entries:
        return
    env["TOOLS"] = ",".join(entry["id"] for entry in entries)
    for entry in entries:
        _add_builtin_tool_config_envs(env, entry["id"], entry.get("config") or {})


def _builtin_tool_entries(value: Any) -> list[dict[str, Any]]:
    if _is_empty(value):
        return []
    raw_entries = value if isinstance(value, list) else [value]
    entries: list[dict[str, Any]] = []
    for raw in raw_entries:
        if isinstance(raw, str):
            tool_id = raw.strip()
            config = {}
        elif isinstance(raw, dict):
            tool_id = str(raw.get("id") or "").strip()
            config = raw.get("config") if isinstance(raw.get("config"), dict) else {}
        else:
            continue
        if tool_id:
            entries.append({"id": tool_id, "config": config})
    return entries


def _add_builtin_tool_config_envs(
    env: dict[str, str],
    tool_id: str,
    config: dict[str, Any],
) -> None:
    mapping = TOOL_CONFIG_ENV.get(tool_id)
    if not mapping:
        return
    for key, env_name in mapping.items():
        value = config.get(key)
        if not _is_empty(value):
            env[env_name] = _stringify(value)


def _add_mcp_router_envs(env: dict[str, str], spec: dict[str, Any]) -> None:
    mcp_router_id = spec.get("mcp_router_id") or spec.get("mcp_toolset_id")
    if _is_empty(mcp_router_id):
        return
    env["MCP_ROUTER_ID"] = _stringify(mcp_router_id)
    tools = [tool for tool in env.get("TOOLS", "").split(",") if tool]
    if "mcp_router" not in tools:
        tools.append("mcp_router")
    env["TOOLS"] = ",".join(tools)


def _component_aliases() -> set[str]:
    return {alias for aliases in COMPONENT_ALIASES.values() for alias in aliases}


def _component_section(spec: dict[str, Any], component: str) -> dict[str, Any]:
    section = spec.get(component)
    if isinstance(section, dict):
        return _flatten_component_config(section)
    for alias in COMPONENT_ALIASES.get(component, ()):
        alias_section = spec.get(alias)
        if isinstance(alias_section, dict):
            return _flatten_component_config(alias_section)
    return {}


def _flatten_component_config(section: dict[str, Any]) -> dict[str, Any]:
    config = section.get("config")
    flat = {key: value for key, value in section.items() if key != "config"}
    if isinstance(config, dict):
        return {**config, **flat}
    return flat


def _component_resource_config(section: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in section.items()
        if key not in {"type", "id", "_id"} and not _is_empty(value)
    }


def _add_harness_enhance_aliases(env: dict[str, str], spec: dict[str, Any]) -> None:
    """Expose harness_enhance fields under the SDK's generic env names too."""

    section = spec.get("harness_enhance")
    if not isinstance(section, dict):
        return
    compression = section.get("compression")
    if not isinstance(compression, dict):
        compression = {}
    verifier = section.get("verifier")
    if not isinstance(verifier, dict):
        verifier = {}

    aliases = {
        "components": "HARNESS_COMPONENTS",
        "profile": "HARNESS_PROFILE",
        "compression_provider": "HARNESS_COMPRESSION_PROVIDER",
        "max_context_chars": "HARNESS_MAX_CONTEXT_CHARS",
        "max_tool_result_chars": "HARNESS_MAX_TOOL_RESULT_CHARS",
        "verifier_mode": "HARNESS_VERIFIER_MODE",
        "store_path": "HARNESS_STORE_PATH",
    }
    nested_aliases = {
        "provider": "HARNESS_COMPRESSION_PROVIDER",
        "max_context_chars": "HARNESS_MAX_CONTEXT_CHARS",
        "max_tool_result_chars": "HARNESS_MAX_TOOL_RESULT_CHARS",
    }
    for key, env_name in aliases.items():
        value = section.get(key)
        if not _is_empty(value):
            env[env_name] = _stringify(value)
    for key, env_name in nested_aliases.items():
        value = compression.get(key)
        if not _is_empty(value):
            env[env_name] = _stringify(value)
    verifier_mode = verifier.get("mode")
    if not _is_empty(verifier_mode):
        env["HARNESS_VERIFIER_MODE"] = _stringify(verifier_mode)
