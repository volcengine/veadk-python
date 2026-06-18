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

"""Top-level ``veadk harness`` command group.

Subcommands scaffold, configure, and deploy the harness server
(:mod:`veadk.cloud.harness_app`) from a layered ``harness.yaml``:

* ``veadk harness create <dir>`` writes a deployable directory: a blank
  ``harness.yaml`` template, a ``.env.example`` (deploy credentials only), a
  ``Dockerfile``, and a short ``README.md``.
* ``veadk harness add`` writes agent parameters into ``harness.yaml``.
* ``veadk harness deploy`` flattens ``harness.yaml`` into runtime env vars and
  performs a cloud AgentKit build + runtime create (no local Docker).

This group is independent of ``veadk agentkit harness``, which is an HTTP client
for an *already deployed* server.
"""

import json
import typing
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import click
import yaml

from veadk.cloud.harness_app.env_mapping import (
    COMPONENT_TYPE_ENV,
    component_connection_params,
    to_runtime_env,
)
from veadk.cloud.harness_app.types import HarnessOverrides

# Default harness/runtime name when `harness_name` is unset in `harness.yaml`
# (mirrors `veadk.cloud.harness_app.app.HARNESS_NAME`).
_DEFAULT_HARNESS_NAME = "default"

# Blank `harness.yaml` template written by `create`. Layered sections map to the
# runtime env names consumed by `veadk.cloud.harness_app` (see env_mapping):
# `model.name` -> MODEL_NAME, `knowledgebase.type` -> KNOWLEDGEBASE_TYPE, a
# backend's params -> DATABASE_<BACKEND>_*. Each line is annotated with its env
# var and the `veadk harness add` flag that sets it.
_HARNESS_YAML = """\
# =============================================================================
# VeADK harness configuration.
#
# `veadk harness deploy` converts this file into the runtime's environment
# variables: top-level fields and `model` are flattened (model.name -> MODEL_NAME,
# tools -> TOOLS, ...); each component's `type` selects its backend, and the
# component's other params map to the VeADK env vars that backend reads (e.g.
# viking `project` -> DATABASE_VIKING_PROJECT). Empty values are skipped, so
# VeADK falls back to its own defaults.
#
# Configure with `veadk harness add ...` or by editing this file. For a
# component, uncomment the params under the backend you set as `type`.
# =============================================================================

# Harness / runtime name (also the knowledgebase & long-term-memory index name).
#   env: HARNESS_NAME          flag: --name
harness_name: ""

# Reasoning model name (Ark auth comes from the runtime's IAM role on deploy).
#   env: MODEL_NAME            flag: --model-name
model:
  name: ""

# Built-in tool names.   env: TOOLS   flag: --tools (comma-separated)
tools: []

# Skill hub names.       env: SKILLS  flag: --skills (comma-separated)
skills: []

# Agent instruction (empty = VeADK default).
#   env: SYSTEM_PROMPT         flag: --system-prompt
system_prompt: ""

# Agent runtime backend: adk (default) | codex.
#   env: RUNTIME               flag: --runtime
runtime: adk

# Structured tool calls via Ark Responses API.
#   env: STRUCTURED_TOOL_CALLS       flag: --structured-tool-calls
#   env: INCLUDE_TOOLS_EVERY_TURN    flag: --include-tools-every-turn
structured_tool_calls: false
include_tools_every_turn: true

# --- Remote A2A Agent discovery / delegation --------------------------------
#   type -> env: REGISTRY_TYPE   flag: --registry
#   "" disables it. Currently supported: agentkit_a2a
# Example:
#   veadk harness add --registry "agentkit://a2a-registry?space_id=xxx&top_k=3"
registry:
  type: ""
  # -- agentkit_a2a -- env REGISTRY_* flags:
  #    --registry-space-id / --registry-top-k / --registry-region
  # space_id: xxx
  # top_k: 3
  # region: cn-beijing

# --- Knowledge base ----------------------------------------------------------
#   type -> env: KNOWLEDGEBASE_TYPE   flag: --knowledgebase-type
#   "" disables it. Supported: viking | opensearch | redis | tos_vector | context_search
knowledgebase:
  type: ""
  # -- viking --      env DATABASE_VIKING_*    flags: --knowledgebase-project / --knowledgebase-region
  # project: my-project
  # region: cn-beijing
  # -- opensearch --  env DATABASE_OPENSEARCH_*  flags: --knowledgebase-host / -port / -username / -password / -use-ssl
  # host: 1.2.3.4
  # port: 9200
  # username: admin
  # password: ""
  # use_ssl: true
  # -- redis --       env DATABASE_REDIS_*     flags: --knowledgebase-host / -port / -username / -password / -db
  # host: 1.2.3.4
  # port: 6379
  # username: default
  # password: ""
  # db: 0

# --- Long-term memory --------------------------------------------------------
#   type -> env: LONG_TERM_MEMORY_TYPE   flag: --long-term-memory-type
#   "" disables it. Supported: viking | opensearch | redis | mem0
long_term_memory:
  type: ""
  # -- viking --      env DATABASE_VIKING_*    flags: --long-term-memory-project / --long-term-memory-region
  # project: my-project
  # region: cn-beijing
  # -- opensearch --  env DATABASE_OPENSEARCH_*  flags: --long-term-memory-host / -port / -username / -password
  # host: 1.2.3.4
  # port: 9200
  # username: admin
  # password: ""
  # -- redis --       env DATABASE_REDIS_*     flags: --long-term-memory-host / -port / -password / -db
  # host: 1.2.3.4
  # port: 6379
  # password: ""
  # db: 0
  # -- mem0 --        env DATABASE_MEM0_*      flags: --long-term-memory-api-key / -api-key-id / -project-id / -base-url
  # api_key: ""
  # api_key_id: ""
  # project_id: ""
  # base_url: https://api.mem0.ai/v1

# --- Short-term memory (session store) ---------------------------------------
#   type -> env: SHORT_TERM_MEMORY_TYPE   flag: --short-term-memory-type
#   local (default) | sqlite | mysql | postgresql
short_term_memory:
  type: local
  # -- mysql --       env DATABASE_MYSQL_*     flags: --short-term-memory-host / -user / -password / -database / -charset
  # host: 1.2.3.4
  # user: root
  # password: ""
  # database: harness
  # charset: utf8
  # -- postgresql --  env DATABASE_POSTGRESQL_*  flags: --short-term-memory-host / -port / -user / -password / -database
  # host: 1.2.3.4
  # port: 5432
  # user: postgres
  # password: ""
  # database: harness

# --- Authentication (optional) -----------------------------------------------
# Omit this block to deploy with the default API-key auth (key_auth). Add it to
# gate the runtime with OAuth2/JWT (custom_jwt): the API gateway then only accepts
# tokens issued by `discovery_url`'s user pool whose audience is one of
# `allowed_ids`. Set up the user pool / client / external IdP in the Volcengine
# Identity console; the CLI only references them (no secret involved).
#   flags: --discovery-url / --allowed-id
# auth:
#   discovery_url: "https://userpool-<id>.userpool.auth.id.cn-beijing.volces.com/.well-known/openid-configuration"
#   allowed_ids: ["<client-id>"]
"""

# `.env.example` carries ONLY deploy credentials. All model / agent config lives
# in `harness.yaml`; on the runtime, Ark auth is resolved from the IAM role.
_ENV_EXAMPLE = """\
# Volcengine deploy credentials for `veadk harness deploy`. Copy to `.env` and
# fill in. These authenticate the AgentKit cloud build + runtime create.
VOLCENGINE_ACCESS_KEY=
VOLCENGINE_SECRET_KEY=
# VOLCENGINE_REGION=cn-beijing
"""

# Container image for the harness server. The base image's apt mirror is an
# unreachable internal host, so apt is repointed at aliyun; the source branch is
# cloned via the ghfast proxy with a github fallback; uv installs from aliyun.
_DOCKERFILE = """\
FROM agentkit-cn-beijing.cr.volces.com/base/py-simple:python3.12-bookworm-slim-latest
ENV PYTHONUNBUFFERED=1
RUN set -eux; \\
    rm -f /etc/apt/sources.list.d/*; \\
    printf 'deb http://mirrors.aliyun.com/debian bookworm main contrib non-free non-free-firmware\\n\\
deb http://mirrors.aliyun.com/debian bookworm-updates main contrib non-free non-free-firmware\\n\\
deb http://mirrors.aliyun.com/debian-security bookworm-security main contrib non-free non-free-firmware\\n' \\
        > /etc/apt/sources.list; \\
    apt-get update; \\
    apt-get install -y --no-install-recommends git ca-certificates; \\
    rm -rf /var/lib/apt/lists/*
WORKDIR /app
RUN set -eux; \\
    for url in \\
        https://ghfast.top/https://github.com/volcengine/veadk-python.git \\
        https://github.com/volcengine/veadk-python.git ; do \\
      for i in 1 2 3; do \\
        git clone --depth 1 -b feat/harness-runtime "$url" src && break 2 || sleep 8; \\
      done; \\
    done; \\
    test -d src/veadk
RUN uv pip install --system --index-url https://mirrors.aliyun.com/pypi/simple/ \\
        ./src fastapi "uvicorn[standard]"
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "veadk.cloud.harness_app.app:app", "--host", "0.0.0.0", "--port", "8000"]
"""

_README = """\
# Harness deployment directory

Deploys the VeADK harness server (`veadk.cloud.harness_app.app:app`) as a
Volcengine **AgentKit runtime** (cloud build, no local Docker).

## Files

- `harness.yaml` — agent configuration; flattened into runtime env vars.
- `.env.example` — Volcengine deploy credentials; copy to `.env` and fill in.
- `Dockerfile` — builds the harness server image.
- `README.md` — this file.

## Usage

1. Configure the agent:

   ```bash
   veadk harness add --harness-name my-harness --model-name doubao-seed-1-6-250615 \\
     --tool web_search --system-prompt "You are a helpful assistant."
   ```

2. Fill in deploy credentials:

   ```bash
   cp .env.example .env   # then set VOLCENGINE_ACCESS_KEY / VOLCENGINE_SECRET_KEY
   ```

3. Deploy (cloud build + runtime create):

   ```bash
   veadk harness deploy
   ```
"""

_CREATE_SUCCESS = """\
Harness deployment directory created at {target}:
- harness.yaml   (agent configuration)
- .env.example   (copy to .env and set VOLCENGINE_ACCESS_KEY / SECRET_KEY)
- Dockerfile     (builds the harness image)
- README.md

Next steps:
  cd {name}
  veadk harness add --harness-name my-harness --model-name <model>
  cp .env.example .env   # then set VOLCENGINE_ACCESS_KEY / VOLCENGINE_SECRET_KEY
  veadk harness deploy
"""


@click.group()
def harness() -> None:
    """Create, configure, and deploy a VeADK harness server."""
    pass


@harness.command("create")
@click.argument("dir_name")
def create(dir_name: str) -> None:
    """Scaffold a deployable harness directory at DIR_NAME.

    Writes a blank `harness.yaml` template, a `.env.example` (deploy credentials
    only), a `Dockerfile`, and a short README. Configure the agent with
    `veadk harness add`, fill in `.env`, then run `veadk harness deploy`.
    """
    target = Path.cwd() / dir_name
    if target.exists() and any(target.iterdir()):
        click.confirm(
            f"Directory '{target}' already exists and is not empty. Overwrite its files?",
            abort=True,
        )

    target.mkdir(parents=True, exist_ok=True)
    (target / "harness.yaml").write_text(_HARNESS_YAML)
    (target / ".env.example").write_text(_ENV_EXAMPLE)
    (target / "Dockerfile").write_text(_DOCKERFILE)
    (target / "README.md").write_text(_README)

    click.secho(_CREATE_SUCCESS.format(target=target, name=dir_name), fg="green")


def _load_harness_yaml(path: Path) -> dict:
    """Load ``harness.yaml`` into a dict; fast-fail when it is missing."""
    if not path.is_file():
        raise click.ClickException(
            f"No `harness.yaml` at '{path}'. Run `veadk harness create` first."
        )
    return yaml.safe_load(path.read_text()) or {}


def _conn_dest(component: str, param: str) -> str:
    """Click dest for a connection flag, e.g. ('long_term_memory','project')."""
    return f"conn__{component}__{param}"


def _is_blank(value: object) -> bool:
    return value is None or value == "" or value == [] or value == {}


def _prune_empty(data: dict) -> None:
    """Drop unset fields so `add` writes only what's configured.

    Empty scalars/lists are removed; a component section with no `type` is
    dropped entirely. ``short_term_memory`` is always kept (its `local` default
    is shown).
    """
    for key in list(data):
        if key == "short_term_memory":
            continue
        value = data[key]
        if isinstance(value, dict):
            for sub in list(value):
                if _is_blank(value[sub]):
                    del value[sub]
            if (
                (key in COMPONENT_TYPE_ENV or key == "registry")
                and not value.get("type")
            ) or not value:
                del data[key]
        elif _is_blank(value):
            del data[key]


_REGISTRY_QUERY_KEYS = {
    "space_id",
    "top_k",
    "endpoint",
    "version",
    "service_name",
    "region",
    "timeout_ms",
    "poll_interval_ms",
}
_REGISTRY_INT_KEYS = {"top_k", "timeout_ms", "poll_interval_ms"}


def _parse_registry_int(key: str, value: object) -> object:
    if key not in _REGISTRY_INT_KEYS:
        return value
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise click.ClickException(
            f"Registry field `{key}` must be an integer, got {value!r}."
        ) from exc


def _parse_registry_uri(value: str) -> dict:
    """Parse the supported AgentKit A2A registry URI into a YAML section."""
    raw = value.strip()
    if raw.lower() in {"", "none", "disabled", "off"}:
        return {"type": ""}

    parsed = urlparse(raw)
    if (
        parsed.scheme != "agentkit"
        or parsed.netloc != "a2a-registry"
        or parsed.path not in {"", "/"}
    ):
        raise click.ClickException(
            "Unsupported registry URI. Currently only "
            "`agentkit://a2a-registry?space_id=xxx&top_k=3` is supported."
        )

    query = {
        key: values[-1]
        for key, values in parse_qs(parsed.query, keep_blank_values=True).items()
    }
    unknown = sorted(set(query) - _REGISTRY_QUERY_KEYS)
    if unknown:
        raise click.ClickException(
            f"Unsupported registry query param(s): {', '.join(unknown)}. "
            f"Known: {', '.join(sorted(_REGISTRY_QUERY_KEYS))}"
        )

    section: dict = {"type": "agentkit_a2a"}
    for key, raw_value in query.items():
        section[key] = _parse_registry_int(key, raw_value)
    return section


def _set_registry_value(section: dict, key: str, value: object | None) -> None:
    if value is not None:
        section[key] = _parse_registry_int(key, value)


def _apply_registry_config(
    data: dict,
    registry: str | None,
    registry_space_id: str | None,
    registry_top_k: int | None,
    registry_endpoint: str | None,
    registry_version: str | None,
    registry_service_name: str | None,
    registry_region: str | None,
    registry_timeout_ms: int | None,
    registry_poll_interval_ms: int | None,
) -> None:
    has_registry_update = any(
        value is not None
        for value in [
            registry,
            registry_space_id,
            registry_top_k,
            registry_endpoint,
            registry_version,
            registry_service_name,
            registry_region,
            registry_timeout_ms,
            registry_poll_interval_ms,
        ]
    )
    if not has_registry_update:
        return

    section = data.get("registry")
    if not isinstance(section, dict):
        section = {}

    if registry is not None:
        section.update(_parse_registry_uri(registry))

    _set_registry_value(section, "space_id", registry_space_id)
    _set_registry_value(section, "top_k", registry_top_k)
    _set_registry_value(section, "endpoint", registry_endpoint)
    _set_registry_value(section, "version", registry_version)
    _set_registry_value(section, "service_name", registry_service_name)
    _set_registry_value(section, "region", registry_region)
    _set_registry_value(section, "timeout_ms", registry_timeout_ms)
    _set_registry_value(section, "poll_interval_ms", registry_poll_interval_ms)

    if section.get("type") != "":
        section["type"] = "agentkit_a2a"

    if section.get("type") == "agentkit_a2a" and not section.get("space_id"):
        raise click.ClickException(
            "Registry space_id is required. Use "
            '`--registry "agentkit://a2a-registry?space_id=xxx"` '
            "or `--registry-space-id xxx`."
        )

    data["registry"] = section


def _connection_options(func):
    """Attach one explicit ``--<component>-<param>`` flag per backend connection param.

    Generated from :data:`env_mapping.COMPONENT_BACKENDS` so the flags stay in sync
    with the backends; each lands in the command's ``**connection`` kwargs.
    """
    for component in reversed(list(COMPONENT_TYPE_ENV)):
        label = component.replace("_", " ")
        for param in reversed(component_connection_params(component)):
            flag = f"--{component.replace('_', '-')}-{param.replace('_', '-')}"
            func = click.option(
                flag,
                _conn_dest(component, param),
                default=None,
                help=f"{label} `{param}` (used when its type needs it).",
            )(func)
    return func


def _override_options(func):
    """Attach a ``--flag`` for every :class:`HarnessOverrides` field.

    Shared by ``add`` and ``invoke`` so their model / tools / skills /
    system-prompt / runtime flags stay identical and in sync with the model —
    adding a field to ``HarnessOverrides`` exposes the flag in both. Each flag
    defaults to ``None`` (unset → not applied).
    """
    for name, field in reversed(list(HarnessOverrides.model_fields.items())):
        option: dict = {
            "default": None,
            "help": field.description or f"`{name}`.",
        }
        if typing.get_origin(field.annotation) is typing.Literal:
            option["type"] = click.Choice(
                [str(arg) for arg in typing.get_args(field.annotation)]
            )
        func = click.option("--" + name.replace("_", "-"), name, **option)(func)
    return func


@harness.command("add")
@click.option(
    "--name",
    "--harness-name",
    "harness_name",
    default=None,
    help="Logical harness / runtime name.",
)
@_override_options
@click.option(
    "--knowledgebase-type",
    "knowledgebase_type",
    default=None,
    help="Knowledge base backend.",
)
@click.option("--long-term-memory-type", default=None, help="Long-term memory backend.")
@click.option(
    "--short-term-memory-type", default=None, help="Short-term memory backend."
)
@click.option(
    "--max-llm-calls",
    "max_llm_calls",
    type=int,
    default=None,
    help="Default max LLM calls per run (overridable per invocation).",
)
@click.option(
    "--structured-tool-calls",
    is_flag=True,
    default=None,
    help="Use Ark Responses API for structured tool calling.",
)
@click.option(
    "--include-tools-every-turn",
    is_flag=True,
    default=None,
    help="Include tool definitions on every model turn.",
)
@click.option(
    "--registry",
    default=None,
    help='AgentKit A2A registry URI, e.g. "agentkit://a2a-registry?space_id=xxx&top_k=3".',
)
@click.option("--registry-space-id", default=None, help="AgentKit A2A SpaceId.")
@click.option(
    "--registry-top-k",
    type=int,
    default=None,
    help="Number of candidate AgentCards to retrieve from the registry.",
)
@click.option(
    "--registry-endpoint",
    default=None,
    help="AgentKit OpenAPI endpoint for A2A registry.",
)
@click.option(
    "--registry-version",
    default=None,
    help="AgentKit OpenAPI version for A2A registry.",
)
@click.option(
    "--registry-service-name",
    default=None,
    help="AgentKit OpenAPI service name for A2A registry.",
)
@click.option("--registry-region", default=None, help="AgentKit OpenAPI region.")
@click.option(
    "--registry-timeout-ms",
    type=int,
    default=None,
    help="A2A registry request / polling timeout in milliseconds.",
)
@click.option(
    "--registry-poll-interval-ms",
    type=int,
    default=None,
    help="A2A task polling interval in milliseconds.",
)
@_connection_options
@click.option(
    "--path",
    default=".",
    help="Harness directory containing harness.yaml (default: current dir).",
)
def add(
    harness_name: str | None,
    knowledgebase_type: str | None,
    long_term_memory_type: str | None,
    short_term_memory_type: str | None,
    max_llm_calls: int | None,
    structured_tool_calls: bool | None,
    include_tools_every_turn: bool | None,
    registry: str | None,
    registry_space_id: str | None,
    registry_top_k: int | None,
    registry_endpoint: str | None,
    registry_version: str | None,
    registry_service_name: str | None,
    registry_region: str | None,
    registry_timeout_ms: int | None,
    registry_poll_interval_ms: int | None,
    path: str,
    model_name: str | None,
    tools: str | None,
    skills: str | None,
    system_prompt: str | None,
    runtime: str | None,
    **connection: str | None,
) -> None:
    """Write agent parameters into `harness.yaml`.

    Options SET their value; `--tools` / `--skills` take comma-separated lists.
    Each backend connection param has its own flag, e.g. `--long-term-memory-project`,
    `--short-term-memory-host` (see `--help`), written under the matching component
    section. `--registry` enables AgentKit A2A registry discovery/delegation.
    Operates on `<path>/harness.yaml`; fast-fails when the file is missing.
    """
    yaml_path = Path(path).resolve() / "harness.yaml"
    data = _load_harness_yaml(yaml_path)
    data.pop("enable_responses", None)
    data.pop("enable_responses_cache", None)

    if harness_name is not None:
        data["harness_name"] = harness_name
    if max_llm_calls is not None:
        data["max_llm_calls"] = max_llm_calls
    if structured_tool_calls is not None:
        data["structured_tool_calls"] = structured_tool_calls
    if include_tools_every_turn is not None:
        data["include_tools_every_turn"] = include_tools_every_turn
    if model_name is not None:
        model = data.get("model")
        if not isinstance(model, dict):
            model = {}
        model["name"] = model_name
        data["model"] = model
    if system_prompt is not None:
        data["system_prompt"] = system_prompt
    if runtime is not None:
        data["runtime"] = runtime
    # Set only the backend `type`, preserving any connection params already set
    # under the component section.
    for type_value, section_key in (
        (knowledgebase_type, "knowledgebase"),
        (long_term_memory_type, "long_term_memory"),
        (short_term_memory_type, "short_term_memory"),
    ):
        if type_value is not None:
            section = data.get(section_key)
            if not isinstance(section, dict):
                section = {}
            section["type"] = type_value
            data[section_key] = section

    if tools is not None:
        data["tools"] = [t.strip() for t in tools.split(",") if t.strip()]
    if skills is not None:
        data["skills"] = [s.strip() for s in skills.split(",") if s.strip()]

    _apply_registry_config(
        data,
        registry,
        registry_space_id,
        registry_top_k,
        registry_endpoint,
        registry_version,
        registry_service_name,
        registry_region,
        registry_timeout_ms,
        registry_poll_interval_ms,
    )

    # Connection params (e.g. --long-term-memory-project) land under their
    # component section, alongside the `type` set above.
    for component in COMPONENT_TYPE_ENV:
        for param in component_connection_params(component):
            value = connection.get(_conn_dest(component, param))
            if value is None:
                continue
            section = data.get(component)
            if not isinstance(section, dict):
                section = {}
                data[component] = section
            section[param] = value

    _prune_empty(data)
    yaml_path.write_text(
        yaml.safe_dump(
            data, sort_keys=False, allow_unicode=True, default_flow_style=None
        )
    )
    click.secho(f"Updated {yaml_path}", fg="green")


@harness.command("show")
@click.option(
    "--path",
    default=".",
    help="Harness directory containing harness.yaml (default: current dir).",
)
def show(path: str) -> None:
    """Show the configured agent params and the per-invoke overridable params.

    Reads `<path>/harness.yaml` (fast-fails when missing) and prints (1) the
    currently configured agent parameters and components, and (2) the params that
    can be overridden per call via `veadk harness invoke`.
    """
    yaml_path = Path(path).resolve() / "harness.yaml"
    data = _load_harness_yaml(yaml_path)

    click.secho(f"Configured agent params ({yaml_path}):", fg="green", bold=True)
    click.echo(
        yaml.safe_dump(
            data, sort_keys=False, allow_unicode=True, default_flow_style=None
        ).rstrip()
    )

    click.echo("")
    click.secho("Overridable at invoke time:", fg="green", bold=True)
    for name, field in HarnessOverrides.model_fields.items():
        flag = "--" + name.replace("_", "-")
        click.echo(f"  {flag}: {field.description or name}")
    click.echo("")
    click.echo(
        "Override per call via `veadk harness invoke ... --<flag>`. "
        "Memory, knowledgebase, and registry are NOT overridable."
    )


def _build_agentkit_config(
    runtime_name: str, region: str, envs: dict[str, str], auth: dict | None = None
) -> dict:
    """Build the cloud AgentKit launch config dict (auto-provision).

    Mirrors the structure `agentkit init` produces for `launch_type: cloud`. The
    `{{account_id}}` / `{{timestamp}}` templates are resolved by AgentKit at
    deploy time and are passed through literally.

    When ``auth`` (a normalized ``{discovery_url, allowed_ids}`` block) is given,
    the runtime is gated by OAuth2/JWT (``custom_jwt``); otherwise it keeps the
    default API-key auth (``key_auth``).
    """
    cloud = {
        "region": region,
        "tos_bucket": "agentkit-platform-{{account_id}}",
        "tos_prefix": "agentkit-builds",
        "image_tag": "{{timestamp}}",
        "cr_instance_name": "agentkit-platform-{{account_id}}",
        "cr_namespace_name": "agentkit",
        "cr_repo_name": runtime_name,
        "cr_auto_create_instance_type": "Micro",
        "build_timeout": 3600,
        "cp_workspace_name": "agentkit-cli-workspace",
        "cp_pipeline_name": "Auto",
        "runtime_id": "Auto",
        "runtime_name": runtime_name,
        "runtime_role_name": "Auto",
    }
    if auth:
        cloud["runtime_auth_type"] = "custom_jwt"
        cloud["runtime_jwt_discovery_url"] = auth["discovery_url"]
        cloud["runtime_jwt_allowed_clients"] = auth["allowed_ids"]
    else:
        cloud["runtime_auth_type"] = "key_auth"
        cloud["runtime_apikey_name"] = "Auto"
        cloud["runtime_apikey"] = "Auto"
        cloud["runtime_jwt_allowed_clients"] = []
    return {
        "common": {
            "agent_name": runtime_name,
            "entry_point": "app.py",
            "description": "Harness Server - VeADK",
            "language": "Python",
            "language_version": "3.12",
            "runtime_envs": envs,
            "launch_type": "cloud",
        },
        "launch_types": {"cloud": cloud},
        "docker_build": {},
    }


def _harness_request(url: str, path: str, key: str | None, body: dict) -> dict:
    """POST ``body`` to ``url + path`` with optional Bearer auth; return JSON."""
    import os

    import httpx

    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"

    # Tool/skill-driven agent runs can take minutes; allow a generous, tunable
    # client timeout (HARNESS_TIMEOUT seconds, default 600).
    timeout = float(os.getenv("HARNESS_TIMEOUT", "600"))
    resp = httpx.post(
        url.rstrip("/") + path, json=body, headers=headers, timeout=timeout
    )
    if resp.status_code != 200:
        raise click.ClickException(
            f"{path} failed: HTTP {resp.status_code} - {resp.text}"
        )
    return resp.json()


def _harness_json_path(directory: str) -> Path:
    return Path(directory).resolve() / "harness.json"


def _load_harness_json(directory: str) -> dict:
    """Load the `{name: {url, key, runtime_id}}` registry, or {} if absent."""
    path = _harness_json_path(directory)
    return json.loads(path.read_text()) if path.is_file() else {}


def _record_harness(
    directory: str,
    name: str,
    url: str,
    runtime_id: str,
    *,
    key: str | None = None,
    auth: dict | None = None,
) -> Path:
    """Record/replace a deployed harness in `harness.json`.

    key_auth records `{url, key, runtime_id}`; custom_jwt records
    `{url, runtime_id, auth_type, discovery_url, allowed_ids}` (no key — a
    user-pool JWT is supplied per request, not stored).
    """
    path = _harness_json_path(directory)
    data = _load_harness_json(directory)
    if auth:
        data[name] = {
            "url": url,
            "runtime_id": runtime_id,
            "auth_type": "custom_jwt",
            "discovery_url": auth["discovery_url"],
            "allowed_ids": auth["allowed_ids"],
        }
    else:
        data[name] = {"url": url, "key": key or "", "runtime_id": runtime_id}
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    return path


def _resolve_auth(
    yaml_auth: dict | None, discovery_url: str | None, allowed_id: str | None
) -> dict | None:
    """Merge the `harness.yaml` `auth` block with deploy flag overrides.

    Returns a normalized ``{discovery_url, allowed_ids}`` to deploy with OAuth2/JWT
    (custom_jwt), or ``None`` to keep the default API-key auth — the presence of an
    `auth` block (or the flags) is the switch. Fails fast on a partial config.
    """
    auth = dict(yaml_auth) if yaml_auth else {}
    if discovery_url:
        auth["discovery_url"] = discovery_url
    if allowed_id:
        auth["allowed_ids"] = [s.strip() for s in allowed_id.split(",") if s.strip()]
    if not auth:
        return None
    discovery = auth.get("discovery_url")
    allowed = auth.get("allowed_ids") or []
    if not discovery or not allowed:
        raise click.ClickException(
            "OAuth deploy needs both `auth.discovery_url` and `auth.allowed_ids` "
            "(or --discovery-url and --allowed-id)."
        )
    return {"discovery_url": discovery, "allowed_ids": list(allowed)}


@harness.command("deploy")
@click.option("--volcengine-access-key", default=None, help="Volcengine access key.")
@click.option("--volcengine-secret-key", default=None, help="Volcengine secret key.")
@click.option(
    "--region",
    default=None,
    help="AgentKit region (default `cn-beijing` or VOLCENGINE_REGION).",
)
@click.option(
    "--path",
    default=".",
    help="Harness directory (created by `veadk harness create`).",
)
@click.option(
    "--discovery-url",
    default=None,
    help="OIDC discovery URL; enables OAuth2/JWT auth (overrides `auth.discovery_url`).",
)
@click.option(
    "--allowed-id",
    default=None,
    help="Comma-separated allowed client IDs for OAuth2/JWT auth (overrides `auth.allowed_ids`).",
)
def deploy(
    volcengine_access_key: str | None,
    volcengine_secret_key: str | None,
    region: str | None,
    path: str,
    discovery_url: str | None,
    allowed_id: str | None,
) -> None:
    """Deploy the harness as an AgentKit runtime (cloud build, no local Docker).

    Loads `harness.yaml`, flattens it into the runtime's environment, and runs an
    AgentKit cloud build + runtime create. Run from inside a directory created by
    `veadk harness create` (containing `harness.yaml` and the `Dockerfile`).
    """
    import os

    from agentkit.toolkit import sdk
    from agentkit.toolkit.models import PreflightMode
    from agentkit.toolkit.reporter import LoggingReporter

    from veadk.utils.logger import get_logger

    logger = get_logger(__name__)

    proj_dir = Path(path).resolve()
    if not proj_dir.is_dir():
        raise click.ClickException(f"Path '{proj_dir}' is not a directory.")

    data = _load_harness_yaml(proj_dir / "harness.yaml")
    runtime_envs = to_runtime_env(data)
    runtime_name = data.get("harness_name") or _DEFAULT_HARNESS_NAME
    auth = _resolve_auth(data.get("auth"), discovery_url, allowed_id)

    # AgentKit authenticates via the Volcengine SDK, which reads VOLC_ACCESSKEY /
    # VOLC_SECRETKEY from the environment. Mirror whatever AK/SK was passed (or
    # already set as VOLCENGINE_*) into those names.
    access_key = volcengine_access_key or os.getenv("VOLCENGINE_ACCESS_KEY", "")
    secret_key = volcengine_secret_key or os.getenv("VOLCENGINE_SECRET_KEY", "")
    if access_key and secret_key:
        os.environ["VOLC_ACCESSKEY"] = access_key
        os.environ["VOLC_SECRETKEY"] = secret_key
    if not os.getenv("VOLC_ACCESSKEY") or not os.getenv("VOLC_SECRETKEY"):
        raise click.ClickException(
            "Volcengine credentials are required. Pass --volcengine-access-key / "
            "--volcengine-secret-key, or set VOLCENGINE_ACCESS_KEY / "
            "VOLCENGINE_SECRET_KEY."
        )

    resolved_region = region or os.getenv("VOLCENGINE_REGION") or "cn-beijing"
    cfg = _build_agentkit_config(runtime_name, resolved_region, runtime_envs, auth)

    # AgentKit's launch path exposes no hook for runtime tags, so tag the runtime
    # at creation by wrapping the SDK's create_runtime: every harness runtime is
    # tagged `agentkit:agenttype=harness`. Scoped to this deploy and restored after.
    from agentkit.sdk.runtime import types as _rt_types
    from agentkit.sdk.runtime.client import AgentkitRuntimeClient as _RtClient

    _orig_create_runtime = _RtClient.create_runtime

    def _create_runtime_with_harness_tag(self, request):
        request.tags = [
            *(request.tags or []),
            _rt_types.TagsItemForCreateRuntime.model_validate(
                {"Key": "agentkit:agenttype", "Value": "harness"}
            ),
        ]
        return _orig_create_runtime(self, request)

    logger.info(f"Deploying harness runtime '{runtime_name}' from {proj_dir}")
    cwd = os.getcwd()
    os.chdir(proj_dir)
    _RtClient.create_runtime = _create_runtime_with_harness_tag
    try:
        result = sdk.launch(
            config_dict=cfg,
            preflight_mode=PreflightMode.WARN,
            reporter=LoggingReporter(),
        )
    finally:
        _RtClient.create_runtime = _orig_create_runtime
        os.chdir(cwd)

    if not result.success:
        raise click.ClickException(f"Harness deploy failed: {result.error}")

    deploy_result = result.deploy_result
    # The AgentKit runner returns the created runtime's id / endpoint / api key in
    # the deploy result's metadata (key auth). Surface them so the user can invoke
    # immediately.
    meta = deploy_result.metadata if (deploy_result and deploy_result.metadata) else {}
    endpoint = deploy_result.endpoint_url if deploy_result else None
    apikey = meta.get("runtime_apikey")
    runtime_id = meta.get("runtime_id")

    lines = [f"Harness runtime deployed: name={runtime_name}"]
    if runtime_id:
        lines.append(f"Runtime id: {runtime_id}")
    lines.append(f"Endpoint:   {endpoint or '(see AgentKit console)'}")
    if auth:
        lines.append("Auth:       custom_jwt (OAuth2/JWT gateway)")
        lines.append(f"Discovery:  {auth['discovery_url']}")
        lines.append(f"Allowed ids: {', '.join(auth['allowed_ids'])}")
    elif apikey:
        lines.append(f"API key:    {apikey}")

    if endpoint:
        json_path = _record_harness(
            path, runtime_name, endpoint, runtime_id or "", key=apikey, auth=auth
        )
        lines.append("")
        if auth:
            lines.append(
                f"Recorded in {json_path}. Auth is OAuth2/JWT — invoking requires an "
                "`Authorization: Bearer <user-pool JWT>` header (the CLI does not mint it)."
            )
        else:
            lines.append(f"Recorded in {json_path}. Invoke it with:")
            lines.append(
                f'  veadk harness invoke --name {runtime_name} --message "<message>"'
            )
    click.secho(
        "\n".join(lines),
        fg="green",
    )


@harness.command("invoke")
@click.argument("message_arg", metavar="[MESSAGE]", required=False)
@click.option(
    "--name",
    "--harness",
    "harness_name",
    required=True,
    help="Harness name; its url/key are read from harness.json unless overridden.",
)
@click.option("--message", "-m", "message_opt", default=None, help="Message to send.")
@click.option(
    "--user-id", "user_id", default="cli-user", help="User id for the session."
)
@click.option(
    "--session-id",
    "session_id",
    default="cli-session",
    help="Session id for the call.",
)
@click.option(
    "--max-llm-calls",
    "max_llm_calls",
    type=int,
    default=None,
    help="Override max LLM calls for this call (falls back to the harness default).",
)
@click.option(
    "--url",
    default=None,
    envvar="HARNESS_URL",
    help="Harness URL (default: harness.json[name], or HARNESS_URL).",
)
@click.option(
    "--key",
    default=None,
    envvar="HARNESS_KEY",
    help="API key for Bearer auth (default: harness.json[name], or HARNESS_KEY).",
)
@click.option(
    "--path",
    default=".",
    help="Dir containing harness.json (default: current dir).",
)
@_override_options
def invoke(
    message_arg,
    harness_name,
    message_opt,
    user_id,
    session_id,
    max_llm_calls,
    url,
    key,
    path,
    **overrides,
) -> None:
    """Invoke a deployed harness and print its output.

    Pass the prompt as the MESSAGE argument or via `--message`. The harness `url`
    and `key` are read from `harness.json` (written by `deploy`) by `--name`,
    unless given explicitly. Any override flag (generated from ``HarnessOverrides``,
    e.g. `--tools`, `--system-prompt`) applies a once-time override on top of the
    deployed agent for this single call; memory and the knowledge base are never
    overridable.
    """
    message = message_opt or message_arg
    if not message:
        raise click.ClickException("Provide a prompt (MESSAGE argument or --message).")

    if not url or not key:
        record = _load_harness_json(path).get(harness_name, {})
        url = url or record.get("url")
        key = key or record.get("key")
    if not url:
        raise click.ClickException(
            f"No URL for '{harness_name}'. Deploy it first (records harness.json) "
            "or pass --url/--key."
        )

    run_agent_request: dict = {"user_id": user_id, "session_id": session_id}
    if max_llm_calls is not None:
        run_agent_request["max_llm_calls"] = max_llm_calls
    body: dict = {
        "prompt": message,
        "harness_name": harness_name,
        "run_agent_request": run_agent_request,
    }
    override = {name: value for name, value in overrides.items() if value is not None}
    if override:
        body["harness"] = override

    result = _harness_request(url, "/harness/invoke", key, body)
    click.echo(result.get("output", json.dumps(result, ensure_ascii=False)))
