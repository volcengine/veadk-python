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
  ``tools``, ``skills``, ``system_prompt``, ``runtime``) is flattened with VeADK's
  own :func:`veadk.utils.misc.flatten_dict` (the flattener ``set_envs`` uses for
  ``config.yaml``): nested keys joined with ``_``, then upper-cased, lists
  comma-joined. So ``model: {name: x}`` -> ``MODEL_NAME``, ``tools: [a, b]`` ->
  ``TOOLS``.
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

from typing import Any

from veadk.utils.misc import flatten_dict

# Component section -> the harness selector env naming its backend ``type``
# (read by :func:`veadk.cloud.harness_app.utils.config_from_env`).
COMPONENT_TYPE_ENV: dict[str, str] = {
    "knowledgebase": "KNOWLEDGEBASE_TYPE",
    "long_term_memory": "LONG_TERM_MEMORY_TYPE",
    "short_term_memory": "SHORT_TERM_MEMORY_TYPE",
}

# Backend ``type`` -> {harness connection param: VeADK env var}. Mirrors the
# pydantic-settings env prefixes in :mod:`veadk.configs.database_configs`;
# credentials map to the shared top-level ``VOLCENGINE_*`` vars. Backends with no
# connection params map to an empty dict (so a stray param fast-fails as a typo).
BACKEND_ENV: dict[str, dict[str, str]] = {
    "viking": {
        "project": "DATABASE_VIKING_PROJECT",
        "region": "DATABASE_VIKING_REGION",
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
    backend ``type`` or connection param raises ``ValueError`` (fast-fail on a
    typo rather than silently dropping config).
    """
    env: dict[str, str] = {}

    # Non-component fields: reuse VeADK's flatten_dict (same as config.yaml).
    # The `auth` block is excluded too: it configures the runtime's gateway
    # authorizer at deploy time (custom_jwt), not the container environment.
    rest = {
        k: v for k, v in spec.items() if k not in COMPONENT_TYPE_ENV and k != "auth"
    }
    for key, value in flatten_dict(rest).items():
        if _is_empty(value):
            continue
        env[key.upper()] = _stringify(value)

    _add_harness_enhance_aliases(env, spec)

    # Component sections: `type` selector + backend-specific connection params.
    for component, type_env in COMPONENT_TYPE_ENV.items():
        section: dict[str, Any] = spec.get(component) or {}
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
        for param, value in section.items():
            if param == "type" or _is_empty(value):
                continue
            env_name = params.get(param)
            if env_name is None:
                raise ValueError(
                    f"Unknown param '{param}' for {component} backend '{backend}'. "
                    f"Known: {sorted(params)}"
                )
            env[env_name] = _stringify(value)

    return env


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
