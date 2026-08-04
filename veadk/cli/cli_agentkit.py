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

from collections.abc import Callable
from pathlib import Path
from typing import cast

import click
from agentkit.toolkit.cli.cli import app as agentkit_typer_app
from typer.main import get_command

_AGENTKIT_INVOKE_COMMAND_NOT_LOADED = object()
_agentkit_invoke_command: Callable[..., object] | None | object = (
    _AGENTKIT_INVOKE_COMMAND_NOT_LOADED
)


@click.group()
def agentkit():
    """AgentKit-compatible commands"""
    pass


agentkit_commands = get_command(agentkit_typer_app)

# Re-export the AgentKit CLI's subcommands under `veadk agentkit`. Iterate by
# duck-typing on `.commands` rather than gating on `isinstance(..., click.Group)`:
# since Typer 0.26 a TyperGroup is no longer a click.Group subclass, so the
# isinstance check silently evaluates False and drops every command.
_agentkit_invoke_click_command: click.Command | None = None
for cmd_name, cmd in getattr(agentkit_commands, "commands", {}).items():
    if cmd_name == "invoke":
        if isinstance(cmd, click.Command):
            _agentkit_invoke_click_command = cmd
        continue
    agentkit.add_command(cmd, name=cmd_name)


@agentkit.command("invoke")
@click.argument("message", required=False)
@click.option("--config-file", type=click.Path(), default=None)
@click.option("--payload", "-p", default=None, help="JSON payload to send.")
@click.option("--headers", "-h", default=None, help="JSON headers to send.")
@click.option("--runtime-id", "-r", default=None)
@click.option("--endpoint", "-e", default=None)
@click.option("--region", default=None)
@click.option("--a2a", is_flag=True, default=False)
@click.option("--show-reasoning", is_flag=True, default=False)
@click.option("--raw", is_flag=True, default=False)
@click.option("--apikey", "-ak", default=None)
@click.option("--harness", default=None, help="Harness name for HarnessApp Runtime.")
@click.option("--model-id", default=None, help="One-shot model override.")
@click.option("--tools", default=None, help="Comma-separated one-shot tool override.")
@click.option("--skills", default=None, help="Comma-separated one-shot skill override.")
@click.option("--system-prompt", default=None, help="One-shot system prompt override.")
@click.option("--runtime", default=None, help="One-shot runtime override.")
@click.option("--user-id", default="agentkit_user")
@click.option("--session-id", default="agentkit_sample_session")
@click.option("--max-llm-calls", type=int, default=None)
@click.option(
    "--enable-harness-enhance",
    is_flag=True,
    default=False,
    help="Enable Harness enhancement headers for this invocation.",
)
@click.option(
    "--harness-components",
    default=None,
    help="Comma-separated Harness components.",
)
@click.option("--harness-profile", default=None)
@click.option("--harness-compression-provider", default=None)
def invoke(
    message: str | None,
    config_file: str | None,
    payload: str | None,
    headers: str | None,
    runtime_id: str | None,
    endpoint: str | None,
    region: str | None,
    a2a: bool,
    show_reasoning: bool,
    raw: bool,
    apikey: str | None,
    harness: str | None,
    model_id: str | None,
    tools: str | None,
    skills: str | None,
    system_prompt: str | None,
    runtime: str | None,
    user_id: str,
    session_id: str,
    max_llm_calls: int | None,
    enable_harness_enhance: bool,
    harness_components: str | None,
    harness_profile: str | None,
    harness_compression_provider: str | None,
) -> None:
    """Invoke AgentKit or HarnessApp Runtime.

    When Harness-specific flags are present, the command sends a HarnessApp
    request to `/harness/invoke` and maps enhancement options to HTTP headers.
    Without those flags it delegates to the upstream AgentKit CLI unchanged.
    """

    if not _is_harness_invoke(
        harness=harness,
        model_id=model_id,
        tools=tools,
        skills=skills,
        system_prompt=system_prompt,
        runtime=runtime,
        enable_harness_enhance=enable_harness_enhance,
        harness_components=harness_components,
        harness_profile=harness_profile,
        harness_compression_provider=harness_compression_provider,
        max_llm_calls=max_llm_calls,
    ):
        _delegate_agentkit_invoke(
            config_file=Path(config_file) if config_file else None,
            message=message,
            payload=payload,
            headers=headers,
            runtime_id=runtime_id,
            endpoint=endpoint,
            region=region,
            a2a=a2a,
            show_reasoning=show_reasoning,
            raw=raw,
            apikey=apikey,
        )
        return

    if config_file or runtime_id or region or a2a or show_reasoning:
        raise click.ClickException(
            "HarnessApp invoke supports --endpoint and Harness-specific flags; "
            "do not combine it with --config-file, --runtime-id, --region, --a2a, "
            "or --show-reasoning."
        )
    if not endpoint:
        raise click.ClickException("HarnessApp invoke requires --endpoint.")

    request_body = _build_harness_body(
        message=message,
        payload=payload,
        harness=harness,
        user_id=user_id,
        session_id=session_id,
        max_llm_calls=max_llm_calls,
        model_id=model_id,
        tools=tools,
        skills=skills,
        system_prompt=system_prompt,
        runtime=runtime,
        enable_harness_enhance=enable_harness_enhance,
        harness_components=harness_components,
        harness_profile=harness_profile,
        harness_compression_provider=harness_compression_provider,
    )
    request_headers = _build_harness_headers(
        headers=headers,
        apikey=apikey,
        enable_harness_enhance=enable_harness_enhance,
        harness_components=harness_components,
        harness_profile=harness_profile,
        harness_compression_provider=harness_compression_provider,
    )
    response = _post_harness_invoke(endpoint, request_body, request_headers)
    if raw:
        click.echo(_json_dumps(response))
        return
    output = response.get("output")
    click.echo(output if output is not None else _json_dumps(response))


def _is_harness_invoke(**values: object) -> bool:
    return any(value is not None and value is not False for value in values.values())


def _delegate_agentkit_invoke(
    *,
    config_file: Path | None,
    message: str | None,
    payload: str | None,
    headers: str | None,
    runtime_id: str | None,
    endpoint: str | None,
    region: str | None,
    a2a: bool,
    show_reasoning: bool,
    raw: bool,
    apikey: str | None,
) -> None:
    invoke_command = _load_agentkit_invoke_command()
    if invoke_command is not None:
        invoke_command(
            config_file=config_file,
            message=message,
            payload=payload,
            headers=headers,
            runtime_id=runtime_id,
            endpoint=endpoint,
            region=region,
            a2a=a2a,
            show_reasoning=show_reasoning,
            raw=raw,
            apikey=apikey,
        )
        return
    if _agentkit_invoke_click_command is None:
        raise click.ClickException(
            "Installed AgentKit CLI does not expose an invoke command."
        )
    _agentkit_invoke_click_command.main(
        args=_agentkit_invoke_args(
            config_file=config_file,
            message=message,
            payload=payload,
            headers=headers,
            runtime_id=runtime_id,
            endpoint=endpoint,
            region=region,
            a2a=a2a,
            show_reasoning=show_reasoning,
            raw=raw,
            apikey=apikey,
        ),
        prog_name="invoke",
        standalone_mode=False,
    )


def _load_agentkit_invoke_command() -> Callable[..., object] | None:
    global _agentkit_invoke_command
    if _agentkit_invoke_command is _AGENTKIT_INVOKE_COMMAND_NOT_LOADED:
        try:
            from agentkit.toolkit.cli.cli import invoke_command
        except ImportError:
            _agentkit_invoke_command = None
        else:
            _agentkit_invoke_command = invoke_command
    return cast(Callable[..., object] | None, _agentkit_invoke_command)


def _agentkit_invoke_args(
    *,
    config_file: Path | None,
    message: str | None,
    payload: str | None,
    headers: str | None,
    runtime_id: str | None,
    endpoint: str | None,
    region: str | None,
    a2a: bool,
    show_reasoning: bool,
    raw: bool,
    apikey: str | None,
) -> list[str]:
    args: list[str] = []
    commands = getattr(_agentkit_invoke_click_command, "commands", {})
    if isinstance(commands, dict) and "run" in commands:
        args.append("run")
    _append_option(args, "--config-file", str(config_file) if config_file else None)
    _append_option(args, "--payload", payload)
    _append_option(args, "--headers", headers)
    _append_option(args, "--runtime-id", runtime_id)
    _append_option(args, "--endpoint", endpoint)
    _append_option(args, "--region", region)
    _append_flag(args, "--a2a", a2a)
    _append_flag(args, "--show-reasoning", show_reasoning)
    _append_flag(args, "--raw", raw)
    _append_option(args, "--apikey", apikey)
    if message is not None:
        args.append(message)
    return args


def _append_option(args: list[str], name: str, value: str | None) -> None:
    if value is not None:
        args.extend([name, value])


def _append_flag(args: list[str], name: str, enabled: bool) -> None:
    if enabled:
        args.append(name)


def _build_harness_body(
    *,
    message: str | None,
    payload: str | None,
    harness: str | None,
    user_id: str,
    session_id: str,
    max_llm_calls: int | None,
    model_id: str | None,
    tools: str | None,
    skills: str | None,
    system_prompt: str | None,
    runtime: str | None,
    enable_harness_enhance: bool,
    harness_components: str | None,
    harness_profile: str | None,
    harness_compression_provider: str | None,
) -> dict[str, object]:
    payload_data = _json_loads_object(payload) if payload else {}
    prompt = (
        message
        or _string_value(payload_data, "prompt")
        or _string_value(payload_data, "message")
    )
    if not prompt:
        raise click.ClickException(
            "Provide a prompt as MESSAGE, --payload.prompt, or --payload.message."
        )
    run_request: dict[str, object] = {
        "user_id": _string_value(payload_data, "user_id") or user_id,
        "session_id": _string_value(payload_data, "session_id") or session_id,
    }
    if max_llm_calls is not None:
        run_request["max_llm_calls"] = max_llm_calls
    body: dict[str, object] = {
        "prompt": prompt,
        "harness_name": harness
        or _string_value(payload_data, "harness_name")
        or "default",
        "run_agent_request": run_request,
    }
    override = {}
    if model_id is not None:
        override["model_name"] = model_id
    if tools is not None:
        override["tools"] = tools
    if skills is not None:
        override["skills"] = skills
    if system_prompt is not None:
        override["system_prompt"] = system_prompt
    if runtime is not None:
        override["runtime"] = runtime
    if override:
        body["harness"] = override
    enhance = _json_object_value(payload_data, "harness_enhance")
    if enable_harness_enhance:
        enhance["enabled"] = True
    if harness_components is not None:
        enhance["components"] = harness_components
    if harness_profile is not None:
        enhance["profile"] = harness_profile
    if harness_compression_provider is not None:
        enhance["compression_provider"] = harness_compression_provider
    if enhance:
        enhance.setdefault("enabled", False)
        body["harness_enhance"] = enhance
    return body


def _build_harness_headers(
    *,
    headers: str | None,
    apikey: str | None,
    enable_harness_enhance: bool,
    harness_components: str | None,
    harness_profile: str | None,
    harness_compression_provider: str | None,
) -> dict[str, str]:
    request_headers = {"Content-Type": "application/json"}
    request_headers.update(
        {key: str(value) for key, value in _json_loads_object(headers).items()}
        if headers
        else {}
    )
    if apikey and "Authorization" not in request_headers:
        request_headers["Authorization"] = f"Bearer {apikey}"
    if enable_harness_enhance:
        request_headers["X-Harness-Enhance"] = "true"
    if harness_components:
        request_headers["X-Harness-Components"] = harness_components
    if harness_profile:
        request_headers["X-Harness-Profile"] = harness_profile
    if harness_compression_provider:
        request_headers["X-Harness-Compression-Provider"] = harness_compression_provider
    return request_headers


def _post_harness_invoke(
    endpoint: str, body: dict[str, object], headers: dict[str, str]
) -> dict[str, object]:
    import httpx

    response = httpx.post(
        endpoint.rstrip("/") + "/harness/invoke",
        json=body,
        headers=headers,
        timeout=600,
    )
    if response.status_code != 200:
        raise click.ClickException(
            f"/harness/invoke failed: HTTP {response.status_code} - {response.text}"
        )
    data = response.json()
    if not isinstance(data, dict):
        raise click.ClickException("HarnessApp returned a non-object JSON response.")
    return data


def _json_loads_object(value: str | None) -> dict[str, object]:
    import json

    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise click.ClickException(f"Invalid JSON object: {exc}") from exc
    if not isinstance(parsed, dict):
        raise click.ClickException("Expected a JSON object.")
    return parsed


def _json_dumps(value: object) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, indent=2)


def _string_value(data: dict[str, object], key: str) -> str:
    value = data.get(key)
    return value if isinstance(value, str) else ""


def _json_object_value(data: dict[str, object], key: str) -> dict[str, object]:
    value = data.get(key)
    return dict(value) if isinstance(value, dict) else {}
