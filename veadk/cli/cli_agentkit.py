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

import json

import click
from agentkit.toolkit.cli.cli import app as agentkit_typer_app
from typer.main import get_command


@click.group()
def agentkit():
    """AgentKit-compatible commands"""
    pass


agentkit_commands = get_command(agentkit_typer_app)

if isinstance(agentkit_commands, click.Group):
    for cmd_name, cmd in agentkit_commands.commands.items():
        agentkit.add_command(cmd, name=cmd_name)


# --- Harness server client -------------------------------------------------
# A thin HTTP client for a deployed Harness server (veadk/cloud/harness_app.py),
# which exposes `/harness/add` and `/harness/invoke`. Lives under a dedicated
# `harness` subgroup so it does not shadow the external AgentKit `invoke`.


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


@click.group()
def harness() -> None:
    """Manage and invoke harnesses on a deployed Harness server."""
    pass


@harness.command("add")
@click.option("--name", required=True, help="Harness (agent) name.")
@click.option(
    "--model-name",
    "model_name",
    default=None,
    help="Model name for the harness (defaults to the server's MODEL_NAME).",
)
@click.option(
    "--system-prompt",
    "system_prompt",
    default="You are a helpful assistant.",
    help="System prompt for the harness.",
)
@click.option(
    "--tools",
    default=None,
    help="Comma-separated built-in tool names, e.g. web_search,web_fetch.",
)
@click.option(
    "--skills",
    default=None,
    help="Comma-separated skill hub names, e.g. clawhub/lgwventrue/system-file-handler.",
)
@click.option(
    "--runtime",
    default=None,
    type=click.Choice(["adk", "codex"]),
    help="Agent runtime backend (defaults to the server's 'adk').",
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
def harness_add(
    name, model_name, system_prompt, tools, skills, runtime, url, key
) -> None:
    """Register a new harness on the server."""
    spec: dict = {"system_prompt": system_prompt}
    # Pass the comma-separated strings through; the server splits them.
    if tools:
        spec["tools"] = tools
    if skills:
        spec["skills"] = skills
    if model_name:
        spec["model_name"] = model_name
    if runtime:
        spec["runtime"] = runtime
    result = _harness_request(
        url, "/harness/add", key, {"harness_name": name, "harness": spec}
    )
    click.echo(json.dumps(result, ensure_ascii=False))


@harness.command("invoke")
@click.argument("message")
@click.option(
    "--harness", "harness_name", required=True, help="Harness name to invoke."
)
@click.option(
    "--model-name",
    "model_name",
    default=None,
    help="Override the model for this call (creates a one-time harness).",
)
@click.option(
    "--system-prompt",
    "system_prompt",
    default=None,
    help="Override the system prompt for this call (creates a one-time harness).",
)
@click.option(
    "--tools",
    default=None,
    help="Override tools for this call, comma-separated (creates a one-time harness).",
)
@click.option(
    "--skills",
    default=None,
    help="Override skills for this call, comma-separated (creates a one-time harness).",
)
@click.option(
    "--runtime",
    default=None,
    type=click.Choice(["adk", "codex"]),
    help="Override the runtime for this call (creates a one-time harness).",
)
@click.option(
    "--user-id", "user_id", default="cli-user", help="User id for the session."
)
@click.option(
    "--session-id", "session_id", default="cli-session", help="Session id for the call."
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
def harness_invoke(
    message,
    harness_name,
    model_name,
    system_prompt,
    tools,
    skills,
    runtime,
    user_id,
    session_id,
    url,
    key,
) -> None:
    """Invoke a harness with MESSAGE and print its output."""
    body: dict = {
        "prompt": message,
        "harness_name": harness_name,
        "run_agent_request": {"user_id": user_id, "session_id": session_id},
    }
    # Any of --model-name/--system-prompt/--tools/--skills/--runtime builds a
    # one-time harness that overrides the stored one for this single call (the
    # server replaces the whole agent). tools/skills are passed through as
    # comma-separated strings; the server splits them.
    once: dict = {}
    if model_name:
        once["model_name"] = model_name
    if system_prompt:
        once["system_prompt"] = system_prompt
    if tools:
        once["tools"] = tools
    if skills:
        once["skills"] = skills
    if runtime:
        once["runtime"] = runtime
    if once:
        body["harness"] = once
    result = _harness_request(url, "/harness/invoke", key, body)
    click.echo(result.get("output", json.dumps(result, ensure_ascii=False)))


agentkit.add_command(harness, name="harness")
