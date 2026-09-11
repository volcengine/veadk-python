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

"""Provision an mpa-agent via AgentKit CreateRuntime (FR-15/16).

Matches the Runtime Manager reference: ``CreateRuntime(ArtifactUrl, ToolId,
Envs)`` -> ``ReleaseRuntime`` -> wait Ready -> read the public endpoint and the
key-auth API key. Env changes go through ``CreateRuntime``/``UpdateRuntime``;
``ReleaseRuntime`` carries no envs. The result is normalized so the caller can
seed ``mpa_meta`` identically to the vefaas path.
"""

from __future__ import annotations

import secrets
import time
from typing import Any, Callable

# Verified against existing mpa_agent runtimes on account 2112682748:
# image-based artifacts use ArtifactType="image" (lowercase).
_DEFAULT_ARTIFACT_TYPE = "image"
_READY_TIMEOUT_SECONDS = 900.0
_READY_POLL_SECONDS = 10.0


class MpaRuntimeError(RuntimeError):
    """Raised when the runtime cannot be created, released, or made Ready."""


def _envs_items(envs: dict[str, str]) -> list[Any]:
    from agentkit.sdk.runtime import types as rt

    return [rt.EnvsItemForCreateRuntime(key=k, value=str(v)) for k, v in envs.items()]


def _update_envs_items(envs: dict[str, str]) -> list[Any]:
    from agentkit.sdk.runtime import types as rt

    return [rt.EnvsItemForUpdateRuntime(key=k, value=str(v)) for k, v in envs.items()]


def _public_endpoint(runtime: Any) -> str:
    nets = getattr(runtime, "network_configurations", None) or []
    public = ""
    private = ""
    for net in nets:
        endpoint = str(getattr(net, "endpoint", "") or "")
        if getattr(net, "network_type", "") == "public" and endpoint:
            public = endpoint
        elif endpoint and not private:
            private = endpoint
    return public or private


def _api_key(runtime: Any) -> str:
    auth = getattr(runtime, "authorizer_configuration", None)
    key_auth = getattr(auth, "key_auth", None) if auth else None
    return str(getattr(key_auth, "api_key", "") or "") if key_auth else ""


def _find_runtime_by_name(client: Any, name: str) -> str:
    """Return the sole Runtime id with the exact name, or an empty string."""
    from agentkit.sdk.runtime import types as rt

    matches: list[str] = []
    next_token = ""
    for _ in range(20):
        kwargs: dict[str, Any] = {"page_size": 100}
        if next_token:
            kwargs["next_token"] = next_token
        response = client.list_runtimes(rt.ListRuntimesRequest(**kwargs))
        for runtime in getattr(response, "agent_kit_runtimes", None) or []:
            if str(getattr(runtime, "name", "") or "") != name:
                continue
            runtime_id = str(getattr(runtime, "runtime_id", "") or "")
            if runtime_id:
                matches.append(runtime_id)
        next_token = str(getattr(response, "next_token", "") or "")
        if not next_token:
            break
    unique = list(dict.fromkeys(matches))
    if len(unique) > 1:
        raise MpaRuntimeError(
            f"multiple runtimes have the exact name {name!r}; "
            "use --runtime-name to select an unambiguous retry target"
        )
    return unique[0] if unique else ""


def _release_if_needed(client: Any, runtime_id: str) -> None:
    """Release the runtime only when its status supports it.

    ``CreateRuntime`` auto-releases the first version, so the runtime is usually
    already Creating/Releasing and an explicit ``ReleaseRuntime`` returns
    ``InvalidResourceStatus``. Only call release when the runtime is in a state
    that needs an explicit release (e.g. an idle version awaiting release).
    """
    from agentkit.sdk.runtime import types as rt

    try:
        runtime = client.get_runtime(rt.GetRuntimeRequest(runtime_id=runtime_id))
    except Exception:  # noqa: BLE001 - if we cannot read status, skip release
        return
    status = str(getattr(runtime, "status", "") or "")
    # Auto-release is in progress or done for these states; do not re-release.
    if status in {"Creating", "Releasing", "Deploying", "Ready", "Running"}:
        return
    try:
        client.release_runtime(rt.ReleaseRuntimeRequest(runtime_id=runtime_id))
    except Exception:  # noqa: BLE001 - release is best-effort; wait_ready decides
        pass


def _wait_ready(
    client: Any,
    runtime_id: str,
    *,
    timeout: float,
    poll_interval: float,
    newer_than_version: int | None = None,
    sleep=time.sleep,
) -> Any:
    from agentkit.sdk.runtime import types as rt

    deadline = time.monotonic() + timeout
    while True:
        runtime = client.get_runtime(rt.GetRuntimeRequest(runtime_id=runtime_id))
        status = str(getattr(runtime, "status", "") or "")
        version = int(getattr(runtime, "current_version_number", 0) or 0)
        if status == "Ready" and (
            newer_than_version is None or version > newer_than_version
        ):
            return runtime
        if status in {"Failed", "Error", "Deleted"}:
            raise MpaRuntimeError(
                f"runtime {runtime_id} entered terminal status {status}: "
                + str(getattr(runtime, "status_message", "") or "")
            )
        if time.monotonic() >= deadline:
            raise MpaRuntimeError(
                f"runtime {runtime_id} did not reach Ready within {timeout:.0f}s "
                f"(last status={status})"
            )
        if poll_interval > 0:
            sleep(poll_interval)
        else:
            runtime = client.get_runtime(rt.GetRuntimeRequest(runtime_id=runtime_id))
            status = str(getattr(runtime, "status", "") or "")
            version = int(getattr(runtime, "current_version_number", 0) or 0)
            if status == "Ready" and (
                newer_than_version is None or version > newer_than_version
            ):
                return runtime
            raise MpaRuntimeError(
                f"runtime {runtime_id} not Ready on the expected version "
                f"(status={status}, version={version})"
            )


def provision_runtime(
    client: Any,
    *,
    name: str,
    artifact_url: str,
    tool_id: str,
    role_name: str,
    envs: dict[str, str],
    artifact_type: str = _DEFAULT_ARTIFACT_TYPE,
    min_instance: int = 1,
    max_instance: int = 1,
    enable_key_auth: bool = True,
    resolve_apig_instance_id: Callable[[str], str] | None = None,
    reinject_public_url: bool = False,
    ready_timeout: float = _READY_TIMEOUT_SECONDS,
    poll_interval: float = _READY_POLL_SECONDS,
) -> dict[str, str]:
    """Create + release an AgentKit runtime and normalize the result.

    Args:
        client: An ``AgentkitRuntimeClient``.
        name: Runtime name.
        artifact_url: mpa-agent image URL.
        tool_id: Codex worker tool id to bind.
        role_name: Runtime execution role.
        envs: Runtime env (route A env + SKILL_SPACE_ID + AGENTKIT_TOOL_ID).
        artifact_type: Deployment artifact type; confirmed by a smoke create.
        enable_key_auth: When True (default), the runtime requires an APIG
            key-auth header. When False, the runtime is created without an
            authorizer so unauthenticated probes (e.g. Studio's agent-card
            probe) succeed — use only for throwaway verification instances.
        resolve_apig_instance_id: Callback mapping the public endpoint to the
            APIG gateway id for ``mpa_meta`` (kept injectable for testability).
        reinject_public_url: When True, after the endpoint is known, re-inject
            ``A2A_PUBLIC_URL`` via ``UpdateRuntime(envs=...)`` (never Release).

    Returns:
        ``{public_endpoint, apig_instance_id, runtime_api_key, runtime_id}``.
    """
    from agentkit.sdk.runtime import types as rt

    if not artifact_url.strip():
        raise MpaRuntimeError("artifact_url (mpa-agent image) is required")
    if not tool_id.strip():
        raise MpaRuntimeError("tool_id is required to bind the sandbox")

    authorizer = None
    if enable_key_auth:
        authorizer = rt.AuthorizerForCreateRuntime(
            key_auth=rt.AuthorizerKeyAuthForCreateRuntime(
                api_key_name=f"{name}-{secrets.token_hex(6)}",
                api_key_location="Header",
            )
        )

    runtime_id = _find_runtime_by_name(client, name)
    reused = bool(runtime_id)
    minimum_version: int | None = None
    if reused:
        # Converge an explicitly named retry to the requested image, Tool, and
        # env rather than creating a duplicate or accepting stale config.
        current = client.get_runtime(rt.GetRuntimeRequest(runtime_id=runtime_id))
        minimum_version = int(getattr(current, "current_version_number", 0) or 0)
        client.update_runtime(
            rt.UpdateRuntimeRequest(
                RuntimeId=runtime_id,
                ArtifactType=artifact_type,
                ArtifactUrl=artifact_url,
                ToolId=tool_id,
                RoleName=role_name,
                MinInstance=min_instance,
                MaxInstance=max_instance,
                Envs=_update_envs_items(envs),
                ReleaseEnable=True,
            )
        )
    else:
        create = client.create_runtime(
            rt.CreateRuntimeRequest(
                Name=name,
                ArtifactType=artifact_type,
                ArtifactUrl=artifact_url,
                ToolId=tool_id,
                RoleName=role_name,
                ProjectName="default",
                ClientToken=secrets.token_hex(16),
                MinInstance=min_instance,
                MaxInstance=max_instance,
                AuthorizerConfiguration=authorizer,
                NetworkConfiguration=rt.NetworkForCreateRuntime(
                    enable_public_network=True,
                    enable_private_network=False,
                ),
                Envs=_envs_items(envs),
            )
        )
        runtime_id = str(getattr(create, "runtime_id", "") or "")
        if not runtime_id:
            raise MpaRuntimeError("CreateRuntime returned no runtime id")

    # CreateRuntime auto-releases the first version, so the runtime is already
    # in a Creating/Releasing state. An explicit ReleaseRuntime here fails with
    # InvalidResourceStatus; only release if the runtime is idle and needs it.
    if not reused:
        _release_if_needed(client, runtime_id)
    runtime = _wait_ready(
        client,
        runtime_id,
        timeout=ready_timeout,
        poll_interval=poll_interval,
        newer_than_version=minimum_version,
    )

    public_endpoint = _public_endpoint(runtime)
    api_key = _api_key(runtime)

    if reinject_public_url and public_endpoint:
        current_version = int(getattr(runtime, "current_version_number", 0) or 0)
        merged = dict(envs)
        merged["A2A_PUBLIC_URL"] = public_endpoint
        client.update_runtime(
            rt.UpdateRuntimeRequest(
                RuntimeId=runtime_id,
                Envs=_update_envs_items(merged),
                ReleaseEnable=True,
            )
        )
        # UpdateRuntime with ReleaseEnable starts a new version asynchronously.
        # Do not report success until the version carrying the real public URL
        # is Ready; otherwise Studio reads the old card with <pending-endpoint>.
        runtime = _wait_ready(
            client,
            runtime_id,
            timeout=ready_timeout,
            poll_interval=poll_interval,
            newer_than_version=current_version,
        )
        public_endpoint = _public_endpoint(runtime) or public_endpoint
        api_key = _api_key(runtime) or api_key

    apig_instance_id = ""
    if resolve_apig_instance_id and public_endpoint:
        apig_instance_id = resolve_apig_instance_id(public_endpoint)

    return {
        "public_endpoint": public_endpoint,
        "apig_instance_id": apig_instance_id,
        "runtime_api_key": api_key,
        "runtime_id": runtime_id,
    }
