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
# flattened runtime env names consumed by `veadk.cloud.harness_app` (see
# `flatten`): `model.name` -> MODEL_NAME, `knowledge_base.type` ->
# KNOWLEDGE_BASE_TYPE, etc. Empty values are skipped on flatten.
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
# Fill this in with `veadk harness add ...` or by editing the file. For a
# component, uncomment the params under the backend you set as `type`.
# =============================================================================

# Logical harness name; also the AgentKit runtime name and the knowledge-base /
# long-term-memory index name. Defaults to "default" when empty.  -> HARNESS_NAME
harness_name: ""

# Reasoning model. Only the name is needed; on the AgentKit runtime Ark auth is
# resolved from the runtime's IAM role.                            -> MODEL_NAME
model:
  name: ""

# Built-in tool names.                  -> TOOLS   e.g. [web_search, link_reader]
tools: []

# Skill hub names.                      -> SKILLS  e.g. [clawhub/foo/bar]
skills: []

# Agent instruction. Empty uses the VeADK default.                 -> SYSTEM_PROMPT
system_prompt: ""

# Agent runtime backend: adk (default) | codex.                    -> RUNTIME
runtime: adk

# --- Knowledge base ----------------------------------------------------------
# type: "" disables it. Supported: viking | opensearch | redis |
#       tos_vector | context_search. Uncomment the params for your chosen type.
knowledge_base:
  type: ""
  # -- viking --      (-> DATABASE_VIKING_*; creds from VOLCENGINE_ACCESS/SECRET_KEY)
  # project: my-project
  # region: cn-beijing
  # -- opensearch --  (-> DATABASE_OPENSEARCH_*)
  # host: 1.2.3.4
  # port: 9200
  # username: admin
  # password: ""
  # use_ssl: true
  # -- redis --       (-> DATABASE_REDIS_*)
  # host: 1.2.3.4
  # port: 6379
  # username: default
  # password: ""
  # db: 0

# --- Long-term memory --------------------------------------------------------
# type: "" disables it. Supported: viking | opensearch | redis | mem0.
long_term_memory:
  type: ""
  # -- viking --      (-> DATABASE_VIKING_*)
  # project: my-project
  # region: cn-beijing
  # -- opensearch --  (-> DATABASE_OPENSEARCH_*)
  # host: 1.2.3.4
  # port: 9200
  # username: admin
  # password: ""
  # -- redis --       (-> DATABASE_REDIS_*)
  # host: 1.2.3.4
  # port: 6379
  # password: ""
  # db: 0
  # -- mem0 --        (-> DATABASE_MEM0_*)
  # api_key: ""
  # api_key_id: ""
  # project_id: ""
  # base_url: https://api.mem0.ai/v1

# --- Short-term memory (session store) ---------------------------------------
# type: local (default) | sqlite | mysql | postgresql.
short_term_memory:
  type: local
  # -- mysql --       (-> DATABASE_MYSQL_*)
  # host: 1.2.3.4
  # user: root
  # password: ""
  # database: harness
  # charset: utf8
  # -- postgresql --  (-> DATABASE_POSTGRESQL_*)
  # host: 1.2.3.4
  # port: 5432
  # user: postgres
  # password: ""
  # database: harness
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


def _append_dedup(data: dict, key: str, values: tuple[str, ...]) -> None:
    """Append ``values`` to the list at ``data[key]``, preserving order, deduped."""
    existing = data.get(key) or []
    if not isinstance(existing, list):
        existing = [existing]
    for value in values:
        if value not in existing:
            existing.append(value)
    data[key] = existing


def _conn_dest(component: str, param: str) -> str:
    """Click dest for a connection flag, e.g. ('long_term_memory','project')."""
    return f"conn__{component}__{param}"


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


@harness.command("add")
@click.option("--harness-name", default=None, help="Logical harness / runtime name.")
@click.option("--model-name", default=None, help="Reasoning model name.")
@click.option(
    "--tool",
    "tools",
    multiple=True,
    help="Built-in tool name to append to `tools` (repeatable).",
)
@click.option(
    "--skill",
    "skills",
    multiple=True,
    help="Skill hub name to append to `skills` (repeatable).",
)
@click.option("--system-prompt", default=None, help="System prompt / instruction.")
@click.option(
    "--runtime",
    type=click.Choice(["adk", "codex"]),
    default=None,
    help="Agent runtime backend.",
)
@click.option("--knowledge-base-type", default=None, help="Knowledge base backend.")
@click.option("--long-term-memory-type", default=None, help="Long-term memory backend.")
@click.option(
    "--short-term-memory-type", default=None, help="Short-term memory backend."
)
@_connection_options
@click.option(
    "--path",
    default=".",
    help="Harness directory containing harness.yaml (default: current dir).",
)
def add(
    harness_name: str | None,
    model_name: str | None,
    tools: tuple[str, ...],
    skills: tuple[str, ...],
    system_prompt: str | None,
    runtime: str | None,
    knowledge_base_type: str | None,
    long_term_memory_type: str | None,
    short_term_memory_type: str | None,
    path: str,
    **connection: str | None,
) -> None:
    """Write agent parameters into `harness.yaml`.

    Scalar options SET their value; `--tool` / `--skill` are repeatable and APPEND
    to the lists (deduped). Each backend connection param has its own flag, e.g.
    `--long-term-memory-project`, `--short-term-memory-host` (see `--help`), which
    is written under the matching component section. Operates on
    `<path>/harness.yaml`; fast-fails when the file is missing.
    """
    yaml_path = Path(path).resolve() / "harness.yaml"
    data = _load_harness_yaml(yaml_path)

    if harness_name is not None:
        data["harness_name"] = harness_name
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
        (knowledge_base_type, "knowledge_base"),
        (long_term_memory_type, "long_term_memory"),
        (short_term_memory_type, "short_term_memory"),
    ):
        if type_value is not None:
            section = data.get(section_key)
            if not isinstance(section, dict):
                section = {}
            section["type"] = type_value
            data[section_key] = section

    if tools:
        _append_dedup(data, "tools", tools)
    if skills:
        _append_dedup(data, "skills", skills)

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

    yaml_path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True))
    click.secho(f"Updated {yaml_path}", fg="green")


def _build_agentkit_config(
    runtime_name: str, region: str, envs: dict[str, str]
) -> dict:
    """Build the cloud AgentKit launch config dict (auto-provision).

    Mirrors the structure `agentkit init` produces for `launch_type: cloud`. The
    `{{account_id}}` / `{{timestamp}}` templates are resolved by AgentKit at
    deploy time and are passed through literally.
    """
    return {
        "common": {
            "agent_name": runtime_name,
            "entry_point": "app.py",
            "description": "VeADK harness server",
            "language": "Python",
            "language_version": "3.12",
            "runtime_envs": envs,
            "launch_type": "cloud",
        },
        "launch_types": {
            "cloud": {
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
                "runtime_auth_type": "key_auth",
                "runtime_apikey_name": "Auto",
                "runtime_apikey": "Auto",
                "runtime_jwt_allowed_clients": [],
            }
        },
        "docker_build": {},
    }


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
def deploy(
    volcengine_access_key: str | None,
    volcengine_secret_key: str | None,
    region: str | None,
    path: str,
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
    cfg = _build_agentkit_config(runtime_name, resolved_region, runtime_envs)

    logger.info(f"Deploying harness runtime '{runtime_name}' from {proj_dir}")
    cwd = os.getcwd()
    os.chdir(proj_dir)
    try:
        result = sdk.launch(
            config_dict=cfg,
            preflight_mode=PreflightMode.WARN,
            reporter=LoggingReporter(),
        )
    finally:
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
    if apikey:
        lines.append(f"API key:    {apikey}")
    if endpoint and apikey:
        lines.append("")
        lines.append("Invoke it with:")
        lines.append(
            f'  veadk harness invoke "<message>" --harness {runtime_name} '
            f'--url "{endpoint}" --key "{apikey}"'
        )
    click.secho(
        "\n".join(lines),
        fg="green",
    )


def _override_options(func):
    """Attach a ``--flag`` for every :class:`HarnessOverrides` field.

    The override flags are generated from the model, so adding a field to
    ``HarnessOverrides`` exposes a new CLI flag automatically — there is no second
    place to update. Each flag defaults to ``None`` (unset → omitted from the
    request), preserving the server's partial-override semantics.
    """
    for name, field in reversed(list(HarnessOverrides.model_fields.items())):
        option: dict = {
            "default": None,
            "help": field.description or f"Override `{name}` for this call.",
        }
        if typing.get_origin(field.annotation) is typing.Literal:
            option["type"] = click.Choice(
                [str(arg) for arg in typing.get_args(field.annotation)]
            )
        func = click.option("--" + name.replace("_", "-"), name, **option)(func)
    return func


@harness.command("invoke")
@click.argument("message")
@click.option(
    "--harness", "harness_name", required=True, help="Harness name to invoke."
)
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
    "--url",
    required=True,
    envvar="HARNESS_URL",
    help="Harness server base URL (or set HARNESS_URL).",
)
@click.option(
    "--key",
    default=None,
    envvar="HARNESS_KEY",
    help="Gateway API key for Bearer auth (or set HARNESS_KEY).",
)
@_override_options
def invoke(message, harness_name, user_id, session_id, url, key, **overrides) -> None:
    """Invoke a deployed harness with MESSAGE and print its output.

    Any override flag (generated from ``HarnessOverrides``) applies a once-time
    override on top of the deployed agent for this single call; unset flags are
    omitted, so the server keeps its configured values (memory and the knowledge
    base are never overridable).
    """
    from veadk.cli.cli_agentkit import _harness_request

    body: dict = {
        "prompt": message,
        "harness_name": harness_name,
        "run_agent_request": {"user_id": user_id, "session_id": session_id},
    }
    override = {name: value for name, value in overrides.items() if value is not None}
    if override:
        body["harness"] = override

    result = _harness_request(url, "/harness/invoke", key, body)
    click.echo(result.get("output", json.dumps(result, ensure_ascii=False)))
