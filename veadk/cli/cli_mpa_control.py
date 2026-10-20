# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
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

"""AgentKit Studio control-plane commands for MPA Agents."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable

import click
from pydantic import BaseModel
from pydantic import ValidationError

from veadk.integrations.mpa import (
    MpaAgentOperationRequest,
    MpaControlPlaneClient,
    MpaControlPlaneError,
    MpaExecutionConfigChange,
    MpaProfile,
)


@dataclass(frozen=True)
class _ControlOptions:
    studio_url: str
    token: str
    timeout: float


def _json_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json", by_alias=True, exclude_none=True)
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    return value


def _emit(awaitable: Awaitable[Any]) -> None:
    try:
        result = asyncio.run(awaitable)
    except MpaControlPlaneError as error:
        payload: dict[str, Any] = {
            "error": {
                "code": error.code,
                "statusCode": error.status_code,
                "requestId": error.request_id,
                "retryable": error.retryable,
            }
        }
        if error.current_state is not None:
            payload["error"]["currentState"] = error.current_state
        click.echo(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        if error.status_code in {401, 403}:
            exit_code = 3
        elif error.status_code in {409, 412, 428}:
            exit_code = 4
        elif error.retryable:
            exit_code = 5
        else:
            exit_code = 1
        raise click.exceptions.Exit(exit_code) from error
    except ValueError as error:
        raise click.UsageError("invalid_control_request") from error
    click.echo(json.dumps(_json_value(result), ensure_ascii=False, sort_keys=True))


def _read_json(path: str) -> Any:
    try:
        content = (
            click.get_text_stream("stdin").read()
            if path == "-"
            else Path(path).read_text()
        )
        return json.loads(content)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise click.UsageError("invalid_json_input") from error


def _operation_request(path: str) -> MpaAgentOperationRequest:
    try:
        return MpaAgentOperationRequest.model_validate(_read_json(path))
    except ValidationError as error:
        raise click.UsageError("invalid_request_payload") from error


def _profile(path: str) -> MpaProfile:
    try:
        return MpaProfile.model_validate(_read_json(path))
    except ValidationError as error:
        raise click.UsageError("invalid_profile_payload") from error


def _execution_config_changes(path: str) -> list[MpaExecutionConfigChange]:
    value = _read_json(path)
    if not isinstance(value, list):
        raise click.UsageError("invalid_execution_config_changes")
    try:
        return [MpaExecutionConfigChange.model_validate(item) for item in value]
    except ValidationError as error:
        raise click.UsageError("invalid_execution_config_changes") from error


async def _get_agent_view(
    options: _ControlOptions,
    *,
    mpa_instance_id: str,
    runtime_id: str,
    region: str,
) -> Any:
    async with MpaControlPlaneClient(
        base_url=options.studio_url,
        bearer_token=options.token,
        timeout=options.timeout,
    ) as client:
        return await client.get_agent_view(
            mpa_instance_id, runtime_id=runtime_id, region=region
        )


async def _create_agent(
    options: _ControlOptions,
    *,
    request: MpaAgentOperationRequest,
    idempotency_key: str,
) -> Any:
    async with MpaControlPlaneClient(
        base_url=options.studio_url,
        bearer_token=options.token,
        timeout=options.timeout,
    ) as client:
        return await client.create_agent(request, idempotency_key=idempotency_key)


async def _update_agent(
    options: _ControlOptions,
    *,
    mpa_instance_id: str,
    request: MpaAgentOperationRequest,
    idempotency_key: str,
) -> Any:
    async with MpaControlPlaneClient(
        base_url=options.studio_url,
        bearer_token=options.token,
        timeout=options.timeout,
    ) as client:
        return await client.update_agent(
            mpa_instance_id, request, idempotency_key=idempotency_key
        )


async def _operation_call(
    options: _ControlOptions,
    action: str,
    *,
    operation_id: str = "",
    request: MpaAgentOperationRequest | None = None,
) -> Any:
    async with MpaControlPlaneClient(
        base_url=options.studio_url,
        bearer_token=options.token,
        timeout=options.timeout,
    ) as client:
        if action == "list":
            return await client.list_active_operations()
        if action == "get":
            return await client.get_operation(operation_id)
        if action == "retry" and request is not None:
            return await client.retry_operation(operation_id, request)
        raise ValueError(f"Unsupported operation action: {action}")


async def _profile_call(
    options: _ControlOptions,
    action: str,
    *,
    mpa_instance_id: str,
    runtime_id: str,
    region: str,
    source_profile_id: str = "",
    profile: MpaProfile | None = None,
    idempotency_key: str = "",
    create: bool = False,
    runtime_revision: str = "",
) -> Any:
    async with MpaControlPlaneClient(
        base_url=options.studio_url,
        bearer_token=options.token,
        timeout=options.timeout,
    ) as client:
        if action == "status":
            return await client.get_profile_status(
                mpa_instance_id, runtime_id=runtime_id, region=region
            )
        if action == "apply" and profile is not None:
            return await client.apply_profile(
                mpa_instance_id,
                runtime_id=runtime_id,
                source_profile_id=source_profile_id,
                profile=profile,
                idempotency_key=idempotency_key,
                region=region,
                create=create,
                runtime_revision=runtime_revision,
            )
        raise ValueError(f"Unsupported Profile action: {action}")


async def _session_call(
    options: _ControlOptions,
    action: str,
    *,
    session_id: str,
    runtime_id: str,
    region: str,
    etag: str = "",
    changes: list[MpaExecutionConfigChange] | None = None,
    idempotency_key: str = "",
    target_profile_revision: int = 0,
) -> Any:
    async with MpaControlPlaneClient(
        base_url=options.studio_url,
        bearer_token=options.token,
        timeout=options.timeout,
    ) as client:
        if action == "config-get":
            return await client.get_session_execution_config(
                session_id, runtime_id=runtime_id, region=region
            )
        if action == "config-patch" and changes is not None:
            return await client.patch_session_execution_config(
                session_id,
                runtime_id=runtime_id,
                etag=etag,
                changes=changes,
                region=region,
            )
        if action == "profile-upgrade":
            return await client.upgrade_session_profile(
                session_id,
                runtime_id=runtime_id,
                etag=etag,
                idempotency_key=idempotency_key,
                target_profile_revision=target_profile_revision,
                region=region,
            )
        raise ValueError(f"Unsupported Session action: {action}")


async def _get_delete_preview(
    options: _ControlOptions,
    *,
    mpa_instance_id: str,
    runtime_id: str,
    region: str,
) -> Any:
    async with MpaControlPlaneClient(
        base_url=options.studio_url,
        bearer_token=options.token,
        timeout=options.timeout,
    ) as client:
        return await client.get_delete_preview(
            mpa_instance_id, runtime_id=runtime_id, region=region
        )


@click.group("control")
@click.option(
    "--studio-url",
    default="",
    envvar="VEADK_MPA_STUDIO_URL",
    help="AgentKit Studio BFF base URL.",
)
@click.option(
    "--token",
    default="",
    envvar="VEADK_MPA_STUDIO_TOKEN",
    help="Studio bearer token; never included in command output.",
)
@click.option(
    "--timeout",
    type=click.FloatRange(min=0.001),
    default=30.0,
    show_default=True,
    help="HTTP request timeout in seconds.",
)
@click.pass_context
def control(ctx: click.Context, studio_url: str, token: str, timeout: float) -> None:
    """Manage MPA Agents through the AgentKit Studio control plane."""
    ctx.obj = _ControlOptions(studio_url=studio_url, token=token, timeout=timeout)


@control.command("view")
@click.option("--mpa-instance-id", required=True)
@click.option("--runtime-id", default="")
@click.option("--region", default="all", show_default=True)
@click.pass_obj
def view(
    options: _ControlOptions,
    mpa_instance_id: str,
    runtime_id: str,
    region: str,
) -> None:
    """Show the Studio-owned MPA Agent and Runtime binding view."""
    _emit(
        _get_agent_view(
            options,
            mpa_instance_id=mpa_instance_id,
            runtime_id=runtime_id,
            region=region,
        )
    )


@control.command("create")
@click.option(
    "--request",
    "request_path",
    required=True,
    type=click.Path(dir_okay=False, path_type=str),
    help="Operation request JSON file, or '-' for stdin.",
)
@click.option(
    "--idempotency-key",
    required=True,
    help="Stable caller-persisted key reused for the same logical write.",
)
@click.pass_obj
def create(options: _ControlOptions, request_path: str, idempotency_key: str) -> None:
    """Create an MPA binding through the Studio BFF."""
    request = _operation_request(request_path)
    _emit(_create_agent(options, request=request, idempotency_key=idempotency_key))


@control.command("update")
@click.option("--mpa-instance-id", required=True)
@click.option(
    "--request",
    "request_path",
    required=True,
    type=click.Path(dir_okay=False, path_type=str),
    help="Operation request JSON file, or '-' for stdin.",
)
@click.option(
    "--idempotency-key",
    required=True,
    help="Stable caller-persisted key reused for the same logical write.",
)
@click.pass_obj
def update(
    options: _ControlOptions,
    mpa_instance_id: str,
    request_path: str,
    idempotency_key: str,
) -> None:
    """Update an MPA binding through the Studio BFF."""
    request = _operation_request(request_path)
    _emit(
        _update_agent(
            options,
            mpa_instance_id=mpa_instance_id,
            request=request,
            idempotency_key=idempotency_key,
        )
    )


@control.group("operation")
def operation() -> None:
    """Inspect and retry MPA lifecycle operations."""


@operation.command("list")
@click.pass_obj
def operation_list(options: _ControlOptions) -> None:
    """List active operations owned by the authenticated principal."""
    _emit(_operation_call(options, "list"))


@operation.command("get")
@click.option("--operation-id", required=True)
@click.pass_obj
def operation_get(options: _ControlOptions, operation_id: str) -> None:
    """Get one active or terminal operation."""
    _emit(_operation_call(options, "get", operation_id=operation_id))


@operation.command("retry")
@click.option("--operation-id", required=True)
@click.option(
    "--request",
    "request_path",
    required=True,
    type=click.Path(dir_okay=False, path_type=str),
    help="Original operation request JSON file, or '-' for stdin.",
)
@click.pass_obj
def operation_retry(
    options: _ControlOptions, operation_id: str, request_path: str
) -> None:
    """Retry an operation using its original request identity."""
    _emit(
        _operation_call(
            options,
            "retry",
            operation_id=operation_id,
            request=_operation_request(request_path),
        )
    )


@control.group("profile")
def profile() -> None:
    """Inspect and apply immutable MPA Profile revisions."""


@profile.command("status")
@click.option("--mpa-instance-id", required=True)
@click.option("--runtime-id", required=True)
@click.option("--region", default="cn-beijing", show_default=True)
@click.pass_obj
def profile_status(
    options: _ControlOptions,
    mpa_instance_id: str,
    runtime_id: str,
    region: str,
) -> None:
    """Show the active Profile revision and its ETag."""
    _emit(
        _profile_call(
            options,
            "status",
            mpa_instance_id=mpa_instance_id,
            runtime_id=runtime_id,
            region=region,
        )
    )


@profile.command("apply")
@click.option("--mpa-instance-id", required=True)
@click.option("--runtime-id", required=True)
@click.option("--source-profile-id", required=True)
@click.option(
    "--profile",
    "profile_path",
    required=True,
    type=click.Path(dir_okay=False, path_type=str),
    help="Profile JSON file, or '-' for stdin.",
)
@click.option("--idempotency-key", required=True)
@click.option("--region", default="cn-beijing", show_default=True)
@click.option(
    "--create",
    is_flag=True,
    help="Apply the first Profile to an orphan Runtime.",
)
@click.option(
    "--runtime-revision",
    default="",
    help="Current Runtime revision required for an update apply.",
)
@click.pass_obj
def profile_apply(
    options: _ControlOptions,
    mpa_instance_id: str,
    runtime_id: str,
    source_profile_id: str,
    profile_path: str,
    idempotency_key: str,
    region: str,
    create: bool,
    runtime_revision: str,
) -> None:
    """Apply a Studio Profile to an MPA Runtime binding."""
    _emit(
        _profile_call(
            options,
            "apply",
            mpa_instance_id=mpa_instance_id,
            runtime_id=runtime_id,
            region=region,
            source_profile_id=source_profile_id,
            profile=_profile(profile_path),
            idempotency_key=idempotency_key,
            create=create,
            runtime_revision=runtime_revision,
        )
    )


@control.group("session")
def session() -> None:
    """Inspect and update versioned Session execution configuration."""


@session.command("config-get")
@click.option("--session-id", required=True)
@click.option("--runtime-id", required=True)
@click.option("--region", default="cn-beijing", show_default=True)
@click.pass_obj
def session_config_get(
    options: _ControlOptions, session_id: str, runtime_id: str, region: str
) -> None:
    """Show effective Session configuration and its ETag."""
    _emit(
        _session_call(
            options,
            "config-get",
            session_id=session_id,
            runtime_id=runtime_id,
            region=region,
        )
    )


@session.command("config-patch")
@click.option("--session-id", required=True)
@click.option("--runtime-id", required=True)
@click.option("--etag", required=True)
@click.option(
    "--changes",
    "changes_path",
    required=True,
    type=click.Path(dir_okay=False, path_type=str),
    help="Execution-config change array JSON file, or '-' for stdin.",
)
@click.option("--region", default="cn-beijing", show_default=True)
@click.pass_obj
def session_config_patch(
    options: _ControlOptions,
    session_id: str,
    runtime_id: str,
    etag: str,
    changes_path: str,
    region: str,
) -> None:
    """Apply explicit Session configuration changes with CAS."""
    _emit(
        _session_call(
            options,
            "config-patch",
            session_id=session_id,
            runtime_id=runtime_id,
            region=region,
            etag=etag,
            changes=_execution_config_changes(changes_path),
        )
    )


@session.command("profile-upgrade")
@click.option("--session-id", required=True)
@click.option("--runtime-id", required=True)
@click.option("--etag", required=True)
@click.option("--target-profile-revision", required=True, type=click.IntRange(min=1))
@click.option("--idempotency-key", required=True)
@click.option("--region", default="cn-beijing", show_default=True)
@click.pass_obj
def session_profile_upgrade(
    options: _ControlOptions,
    session_id: str,
    runtime_id: str,
    etag: str,
    target_profile_revision: int,
    idempotency_key: str,
    region: str,
) -> None:
    """Upgrade a Session to a later immutable Profile revision."""
    _emit(
        _session_call(
            options,
            "profile-upgrade",
            session_id=session_id,
            runtime_id=runtime_id,
            region=region,
            etag=etag,
            idempotency_key=idempotency_key,
            target_profile_revision=target_profile_revision,
        )
    )


@control.command("delete-preview")
@click.option("--mpa-instance-id", required=True)
@click.option("--runtime-id", required=True)
@click.option("--region", default="cn-beijing", show_default=True)
@click.pass_obj
def delete_preview(
    options: _ControlOptions,
    mpa_instance_id: str,
    runtime_id: str,
    region: str,
) -> None:
    """Preview authorized cleanup impact without deleting resources."""
    _emit(
        _get_delete_preview(
            options,
            mpa_instance_id=mpa_instance_id,
            runtime_id=runtime_id,
            region=region,
        )
    )
