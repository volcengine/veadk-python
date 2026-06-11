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

Two subcommands scaffold and deploy the harness server
(:mod:`veadk.cloud.harness_app`):

* ``veadk harness create <dir>`` writes a deployable directory documenting every
  harness environment variable in ``.env.example`` (plus a ``Dockerfile`` and an
  ``agentkit.yaml`` preconfigured for an AgentKit runtime deploy).
* ``veadk harness deploy`` builds and pushes the harness Docker image via
  AgentKit, then creates an **AgentKit runtime** from that image.

This group is independent of ``veadk agentkit harness``, which is an HTTP client
for an *already deployed* server.
"""

import json
import typing
from pathlib import Path

import click

from veadk.cloud.harness_app.types import HarnessOverrides

# AgentKit runtime artifact type for a container image (defined in
# `agentkit/toolkit/runners/ve_agentkit.py::ARTIFACT_TYPE_DOCKER_IMAGE`).
_ARTIFACT_TYPE_IMAGE = "image"

# Tag attached to every harness runtime so it can be discovered later. The
# locked requirement is a single tag whose key is the literal "Harness" with no
# value.
_HARNESS_TAG_KEY = "Harness"

# Default harness/runtime name when `HARNESS_NAME` is unset in the `.env`
# (mirrors `veadk.cloud.harness_app.app.HARNESS_NAME`).
_DEFAULT_HARNESS_NAME = "default"

# Documents every harness env var read by `veadk.cloud.harness_app.agent`
# (authoritative source: `harness_app/utils.py::_ENV_FIELDS` and the
# `agent.py` module docstring). Placeholder values are safe defaults; the
# server falls back to VeADK defaults for anything left unset.
_ENV_EXAMPLE = """\
# ---------------------------------------------------------------------------
# Harness server environment variables.
# Copy to `.env` and fill in. Only set what you need; unset vars fall back to
# the VeADK defaults documented below.
# ---------------------------------------------------------------------------

# --- Reasoning model -------------------------------------------------------
# Model name. Unset uses the VeADK default model.
MODEL_AGENT_NAME=doubao-seed-1-6-250615
# Model API credentials / endpoint (Volcengine Ark by default).
MODEL_AGENT_API_KEY=your-ark-api-key
MODEL_AGENT_API_BASE=https://ark.cn-beijing.volces.com/api/v3
MODEL_AGENT_PROVIDER=openai

# --- Agent definition ------------------------------------------------------
# System prompt / instruction. Unset uses the VeADK default instruction.
SYSTEM_PROMPT=You are a helpful assistant.
# Comma-separated built-in tool names, e.g. "web_search,web_fetch".
TOOLS=
# Comma-separated skill hub names, e.g. "clawhub/lgwventrue/system-file-handler".
SKILLS=
# Agent runtime backend: "adk" (default) or "codex".
# "codex" requires the optional codex extra installed on the server.
RUNTIME=adk

# --- Knowledge base & memory ----------------------------------------------
# App/index name for the knowledge base and long-term memory. Default: harness_app.
APP_NAME=harness_app
# Knowledge base backend (e.g. "viking"). Leave empty to disable.
KNOWLEDGEBASE_TYPE=
# Long-term memory backend (e.g. "viking"). Leave empty to disable.
LONGTERM_MEM_TYPE=
# Short-term memory backend (e.g. "local", "mysql"). Default: local.
SHORTTERM_MEM_TYPE=local

# --- Server ----------------------------------------------------------------
# Logical harness name reported in invoke responses. Default: default.
HARNESS_NAME=default
# Skill hub download endpoint. Unset uses the public skill hub.
SKILL_HUB_DOWNLOAD_URL=https://skills.volces.com/v1/skills/download
# Bind host/port. On VeFaaS these are set automatically from the runtime port.
SERVER_HOST=0.0.0.0
SERVER_PORT=8000
"""

# Container image entrypoint, mirroring `veadk/cloud/harness_app/Dockerfile`
# but importing the app from the installed package (no source files copied).
_DOCKERFILE = """\
FROM python:3.12-slim

WORKDIR /app

# `[extensions]` pulls llama-index / redis / opensearch, required when the
# KNOWLEDGEBASE_TYPE or LONGTERM_MEM_TYPE env vars enable those components.
RUN apt-get update && apt-get install -y --no-install-recommends git && \\
    pip3 install --no-cache-dir \\
      "veadk-python[extensions] @ git+https://github.com/volcengine/veadk-python.git" && \\
    apt-get purge -y git && apt-get autoremove -y && \\
    apt-get clean && rm -rf /var/lib/apt/lists/*

# To run with the "codex" runtime (RUNTIME=codex), also install:
#   pip3 install --no-cache-dir openai-codex

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "veadk.cloud.harness_app.app:app", \\
     "--host", "0.0.0.0", "--port", "8000"]
"""

# AgentKit deploy config consumed by `agentkit.toolkit.sdk.build`. `launch_type:
# hybrid` builds the image locally with Docker and pushes it to Container
# Registry, which yields the pushed image URL `veadk harness deploy` feeds to
# CreateRuntime. The hand-written `Dockerfile` above has no AgentKit metadata
# header, so AgentKit keeps it as-is (KEEP_USER_CUSTOM) instead of regenerating.
# `ve_runtime_name` defaults to the harness name; `veadk harness deploy`
# overrides it from `HARNESS_NAME` in the `.env` anyway.
_AGENTKIT_YAML = """\
# AgentKit build config for `veadk harness deploy`. `deploy` runs the hybrid
# build (local Docker build + push to Container Registry) and then creates an
# AgentKit runtime from the pushed image. Set a real `cr_instance_name` (or run
# `agentkit config`) so the image can be pushed; `Auto` skips the push.
common:
  agent_name: harness
  entry_point: app.py
  description: VeADK harness server
  language: Python
  language_version: "3.12"
  launch_type: hybrid
launch_types:
  hybrid:
    region: cn-beijing
    ve_runtime_name: {runtime_name}
    cr_instance_name: Auto
    cr_namespace_name: agentkit
    cr_repo_name: harness
"""

_README = """\
# Harness deployment directory

This directory deploys the VeADK harness server
(`veadk.cloud.harness_app.app:app`) as a Volcengine **AgentKit runtime**.

## Files

- `.env.example` — every harness env var; copy to `.env` and fill in.
- `Dockerfile` — builds the image that serves the harness app.
- `agentkit.yaml` — AgentKit build config (hybrid: local build + push to
  Container Registry). `ve_runtime_name` defaults to the harness name.
- `README.md` — this file.

## Usage

1. Copy `.env.example` to `.env` and fill in the values (model key, tools,
   skills…). Set `HARNESS_NAME`; it becomes the runtime's name (defaults to
   `default` when unset).
2. Set a real Container Registry instance in `agentkit.yaml` (`cr_instance_name`)
   or run `agentkit config` — `Auto` skips the image push and the build cannot
   produce an image URL.
3. From inside this directory, run:

   ```bash
   veadk harness deploy
   ```

`deploy` builds and pushes the Docker image via AgentKit, then creates an
AgentKit runtime named after `HARNESS_NAME` with a `Harness` tag. The env vars
in `.env` become the runtime's environment, so the cloud agent is assembled
exactly as configured here.
"""

_CREATE_SUCCESS = """\
Harness deployment directory created at {target}:
- .env.example   (copy to .env and fill in)
- Dockerfile     (builds the harness image)
- agentkit.yaml  (AgentKit build config; set a real cr_instance_name)
- README.md

Next steps:
  cd {name}
  cp .env.example .env   # then edit it (set HARNESS_NAME)
  # edit agentkit.yaml: set cr_instance_name (or run `agentkit config`)
  veadk harness deploy
"""


@click.group()
def harness() -> None:
    """Create and deploy a VeADK harness server."""
    pass


@harness.command("create")
@click.argument("dir_name")
def create(dir_name: str) -> None:
    """Scaffold a deployable harness directory at DIR_NAME.

    Writes a `.env.example` documenting every harness environment variable, a
    `Dockerfile` that builds the harness image, an `agentkit.yaml` build config,
    and a short README. Copy `.env.example` to `.env`, fill it in, then run
    `veadk harness deploy` from inside the directory.
    """
    target = Path.cwd() / dir_name
    if target.exists() and any(target.iterdir()):
        click.confirm(
            f"Directory '{target}' already exists and is not empty. Overwrite its files?",
            abort=True,
        )

    target.mkdir(parents=True, exist_ok=True)
    (target / ".env.example").write_text(_ENV_EXAMPLE)
    (target / "Dockerfile").write_text(_DOCKERFILE)
    (target / "agentkit.yaml").write_text(
        _AGENTKIT_YAML.format(runtime_name=_DEFAULT_HARNESS_NAME)
    )
    (target / "README.md").write_text(_README)

    click.secho(_CREATE_SUCCESS.format(target=target, name=dir_name), fg="green")


def _read_env_file(env_path: Path) -> dict[str, str]:
    """Parse the harness directory's `.env` into a flat ``{KEY: VALUE}`` dict.

    Returns an empty dict when no `.env` exists. Used both to derive the runtime
    name (`HARNESS_NAME`) and as the runtime's `Envs`.
    """
    from dotenv import dotenv_values

    if not env_path.is_file():
        return {}
    return {k: v for k, v in dotenv_values(env_path).items() if v is not None}


def _build_harness_image(proj_dir: Path) -> str:
    """Build and push the harness image via AgentKit; return the pushed image URL.

    Reuses AgentKit's `sdk.build` (hybrid strategy: local Docker build + push to
    Container Registry). The pushed image URL is read from the build result's
    `metadata["cr_image_url"]` (the push step records it there), falling back to
    the local image's full name. Fast-fails when the build did not push an image.
    """
    from agentkit.toolkit import sdk
    from agentkit.toolkit.reporter import LoggingReporter

    config_file = proj_dir / "agentkit.yaml"
    if not config_file.is_file():
        raise click.ClickException(
            f"No `agentkit.yaml` in '{proj_dir}'. Run `veadk harness create` first."
        )

    result = sdk.build(config_file=str(config_file), reporter=LoggingReporter())
    if not result.success:
        raise click.ClickException(f"Harness image build failed: {result.error}")

    image_url = (result.metadata or {}).get("cr_image_url")
    if not image_url:
        raise click.ClickException(
            "Build succeeded but no image was pushed to Container Registry. Set a "
            "real `cr_instance_name` in `agentkit.yaml` (or run `agentkit config`)."
        )
    return image_url


def _create_harness_runtime(
    *,
    runtime_name: str,
    role_name: str,
    image_url: str,
    envs: dict[str, str],
    region: str,
) -> str:
    """Create an AgentKit runtime for the harness image; return its runtime id.

    Ensures the IAM role exists (CreateRuntime requires it), then issues
    CreateRuntime with the harness name, a `Harness` tag, the `.env` as `Envs`,
    and the pushed image as an `image` artifact.
    """
    from agentkit.sdk.runtime import types as rt
    from agentkit.sdk.runtime.client import AgentkitRuntimeClient
    from agentkit.toolkit.volcengine.iam import VeIAM
    from agentkit.utils.misc import generate_apikey_name, generate_client_token

    if not VeIAM(region=region).ensure_role_for_agentkit(role_name):
        raise click.ClickException(
            f"Failed to create or ensure the runtime IAM role `{role_name}`."
        )

    client = AgentkitRuntimeClient(region=region)
    # The runtime types use by-alias (PascalCase) fields with `populate_by_name`;
    # build the request from an alias-keyed dict via `model_validate` so static
    # type checking matches the API field names exactly.
    request = rt.CreateRuntimeRequest.model_validate(
        {
            "Name": runtime_name,
            "RoleName": role_name,
            "ArtifactType": _ARTIFACT_TYPE_IMAGE,
            "ArtifactUrl": image_url,
            "Envs": [{"Key": k, "Value": v} for k, v in envs.items()],
            "Tags": [{"Key": _HARNESS_TAG_KEY}],
            "AuthorizerConfiguration": {
                "KeyAuth": {
                    "ApiKeyName": generate_apikey_name(),
                    "ApiKeyLocation": "HEADER",
                }
            },
            "ClientToken": generate_client_token(),
        }
    )
    response = client.create_runtime(request)
    return response.runtime_id or ""


@harness.command("deploy")
@click.option("--volcengine-access-key", default=None, help="Volcengine access key.")
@click.option("--volcengine-secret-key", default=None, help="Volcengine secret key.")
@click.option(
    "--region",
    default=None,
    help="AgentKit region (default `cn-beijing` or VOLCENGINE_REGION).",
)
@click.option(
    "--role-name",
    default=None,
    help="Runtime IAM role name (default: auto-generated or HARNESS_RUNTIME_ROLE).",
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
    role_name: str | None,
    path: str,
) -> None:
    """Build the harness image and deploy it as an AgentKit runtime.

    Run this from inside a directory created by `veadk harness create` (with a
    filled-in `.env` and an `agentkit.yaml`). It builds and pushes the harness
    Docker image via AgentKit, then creates an AgentKit runtime whose:

    * Name is the harness name (`HARNESS_NAME` in the `.env`, default `default`),
    * Envs are the directory's `.env`,
    * Tags carry a single `Harness` tag,
    * artifact is the pushed image.
    """
    import os

    from veadk.utils.logger import get_logger

    logger = get_logger(__name__)

    proj_dir = Path(path).resolve()
    if not proj_dir.is_dir():
        raise click.ClickException(f"Path '{proj_dir}' is not a directory.")

    # AgentKit's build/runtime clients authenticate via the Volcengine SDK, which
    # reads VOLC_ACCESSKEY / VOLC_SECRETKEY from the environment. Mirror whatever
    # AK/SK was passed (or already set as VOLCENGINE_*) into those names.
    access_key = volcengine_access_key or os.getenv("VOLCENGINE_ACCESS_KEY", "")
    secret_key = volcengine_secret_key or os.getenv("VOLCENGINE_SECRET_KEY", "")
    if access_key and secret_key:
        os.environ["VOLC_ACCESSKEY"] = access_key
        os.environ["VOLC_SECRETKEY"] = secret_key
    if not os.getenv("VOLC_ACCESSKEY") or not os.getenv("VOLC_SECRETKEY"):
        raise click.ClickException(
            "Volcengine credentials are required. Pass --volcengine-access-key / "
            "--volcengine-secret-key, or set VOLCENGINE_ACCESS_KEY / "
            "VOLCENGINE_SECRET_KEY (or VOLC_ACCESSKEY / VOLC_SECRETKEY)."
        )

    envs = _read_env_file(proj_dir / ".env")
    runtime_name = envs.get("HARNESS_NAME") or _DEFAULT_HARNESS_NAME
    resolved_region = region or os.getenv("VOLCENGINE_REGION") or "cn-beijing"
    resolved_role = role_name or os.getenv("HARNESS_RUNTIME_ROLE")
    if not resolved_role:
        from agentkit.utils.misc import generate_runtime_role_name

        resolved_role = generate_runtime_role_name()

    logger.info(f"Building harness image from {proj_dir}")
    image_url = _build_harness_image(proj_dir)
    logger.info(f"Built harness image: {image_url}")

    runtime_id = _create_harness_runtime(
        runtime_name=runtime_name,
        role_name=resolved_role,
        image_url=image_url,
        envs=envs,
        region=resolved_region,
    )

    click.secho(
        f"Harness runtime created: name={runtime_name} id={runtime_id}\n"
        f"Image: {image_url}\n"
        f"Tagged `{_HARNESS_TAG_KEY}`. Find its endpoint in the AgentKit console "
        "or via the AgentKit SDK (GetRuntime).",
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
