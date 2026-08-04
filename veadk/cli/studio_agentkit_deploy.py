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

"""Shared AgentKit Runtime deployment helpers for Studio-created projects."""

from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Callable, Iterable
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import yaml

_ENV_PREFIXES = (
    "MODEL_",
    "ARK_",
    "VOLCENGINE_",
    "TOOL_",
    "DATABASE_",
    "OBSERVABILITY_",
)


class StudioAgentkitDeployError(RuntimeError):
    """User-facing AgentKit Runtime deployment failure."""

    def __init__(
        self,
        message: str,
        *,
        phase: str = "deploy",
        runtime_id: str = "",
        log_path: str = "",
    ) -> None:
        super().__init__(message)
        self.phase = phase
        self.runtime_id = runtime_id
        self.log_path = log_path


def deploy_agentkit_project(
    *,
    project: dict[str, Any],
    region: str,
    runtime_id: str = "",
    description: str = "",
    project_name: str = "default",
    progress: Callable[[str], None] | None = None,
    author: str = "",
    owner_id: str = "",
) -> dict[str, Any]:
    """Deploy Studio-generated project files to a new or existing Runtime."""
    temp_dir = tempfile.mkdtemp(prefix=f"studio_agentkit_{project['name']}_")
    base = Path(temp_dir).resolve()
    created_runtime_id = ""

    def _record_runtime_created(runtime_id: str, _created: Any) -> None:
        nonlocal created_runtime_id
        created_runtime_id = runtime_id

    try:
        _emit(progress, "Writing AgentProject files...")
        _write_project(project, base)
        cloud_config: dict[str, Any] = {
            "region": region,
            "project_name": project_name,
            "image_tag": "latest",
            "runtime_envs": collect_runtime_envs(),
            "python_version": "3.12",
        }
        if runtime_id:
            cloud_config.update(runtime_update_config(runtime_id, region))
        elif region and region != "cn-beijing":
            cloud_config["tos_bucket"] = tos_bucket_name(region)

        agentkit_config = {
            "common": {
                "agent_name": project["name"],
                "entry_point": "app.py",
                "description": description,
                "python_version": "3.12",
                "launch_type": "cloud",
            },
            "launch_types": {"cloud": cloud_config},
        }
        _emit(progress, "Writing agentkit.yaml...")
        (base / "agentkit.yaml").write_text(
            yaml.dump(agentkit_config, allow_unicode=True),
            encoding="utf-8",
        )

        _emit(progress, "Launching AgentKit Runtime...")
        result = launch_agentkit_config(
            config_file=base / "agentkit.yaml",
            reporter=ProgressReporter(progress) if progress else None,
            runtime_tags=runtime_tags(author=author, owner_id=owner_id),
            on_runtime_created=_record_runtime_created,
        )
        if not getattr(result, "success", False):
            error = getattr(result, "error", None) or result_error_text(result)
            raise StudioAgentkitDeployError(
                str(error or "AgentKit Runtime deployment failed"),
                phase="deploy",
                runtime_id=created_runtime_id or runtime_id,
            )
        deploy_result = getattr(result, "deploy_result", None)
        metadata = (
            (getattr(deploy_result, "metadata", None) or {}) if deploy_result else {}
        )
        deployed_runtime_id = str(metadata.get("runtime_id") or runtime_id)
        if not deployed_runtime_id:
            raise StudioAgentkitDeployError(
                "AgentKit deployment did not return runtimeId",
                phase="deploy",
                runtime_id=created_runtime_id or runtime_id,
            )
        _emit(progress, f"AgentKit Runtime deployed: runtimeId={deployed_runtime_id}")
        return {
            "runtimeId": deployed_runtime_id,
            "agentName": str(metadata.get("runtime_name") or project["name"]),
            "region": region,
            "url": getattr(deploy_result, "endpoint_url", "") if deploy_result else "",
            "version": runtime_version(deployed_runtime_id, region),
            "consoleUrl": (
                "https://console.volcengine.com/agentkit/"
                f"region:agentkit+{region}/runtime?projectName={project_name}"
            ),
        }
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def launch_agentkit_config(
    *,
    config_file: str | Path,
    preflight_mode: Any | None = None,
    reporter: Any | None = None,
    runtime_tags: Iterable[Any] | None = None,
    disable_apmplus: bool = True,
    should_cancel: Callable[[], bool] | None = None,
    on_runtime_created: Callable[[str, Any], None] | None = None,
    on_cancel_created: Callable[[str, Any], None] | None = None,
) -> Any:
    """Launch an AgentKit config with Studio's Runtime creation safeguards."""
    from agentkit.sdk.runtime.client import AgentkitRuntimeClient
    from agentkit.toolkit import sdk
    from agentkit.toolkit.models import PreflightMode

    tags = normalize_runtime_tags(runtime_tags or [])
    selected_preflight_mode = preflight_mode or PreflightMode.WARN
    original_create = AgentkitRuntimeClient.create_runtime

    def _create_with_studio_defaults(self: Any, request: Any) -> Any:
        if should_cancel is not None and should_cancel():
            raise RuntimeError("Deployment cancelled")
        request.tags = [*(getattr(request, "tags", None) or []), *tags]
        if disable_apmplus:
            request.apmplus_enable = False
        created = create_runtime_with_description_fallback(
            original_create, self, request
        )
        runtime_id = _created_runtime_id(created)
        if runtime_id and on_runtime_created is not None:
            on_runtime_created(runtime_id, created)
        if should_cancel is not None and should_cancel():
            if runtime_id and on_cancel_created is not None:
                on_cancel_created(runtime_id, created)
            raise RuntimeError("Deployment cancelled")
        return created

    try:
        AgentkitRuntimeClient.create_runtime = _create_with_studio_defaults
        kwargs: dict[str, Any] = {
            "config_file": str(config_file),
            "preflight_mode": selected_preflight_mode,
        }
        if reporter is not None:
            kwargs["reporter"] = reporter
        return sdk.launch(**kwargs)
    finally:
        AgentkitRuntimeClient.create_runtime = original_create


def create_runtime_with_description_fallback(
    create_runtime: Callable[[Any, Any], Any], client: object, request: Any
) -> Any:
    """Retry Runtime creation once without description if AgentKit rejects it."""
    try:
        return create_runtime(client, request)
    except Exception as error:
        if not is_malformed_runtime_description_error(error) or not getattr(
            request, "description", None
        ):
            raise
        request.description = None
        return create_runtime(client, request)


def is_malformed_runtime_description_error(error: object) -> bool:
    return "invaliddescription.malformed" in str(error or "").lower()


def runtime_tags(*, author: str = "", owner_id: str = "") -> list[Any]:
    tags = [{"Key": "veadk:managed", "Value": "true"}]
    if author:
        tags.append({"Key": "veadk:author", "Value": author})
    if owner_id:
        tags.append({"Key": "veadk:owner", "Value": owner_id})
    return normalize_runtime_tags(tags)


def normalize_runtime_tags(tags: Iterable[Any]) -> list[Any]:
    from agentkit.sdk.runtime import types as _rt

    normalized = []
    for tag in tags:
        if isinstance(tag, dict):
            normalized.append(_rt.TagsItemForCreateRuntime.model_validate(tag))
        else:
            normalized.append(tag)
    return normalized


def collect_runtime_envs(extra_envs: dict[str, str] | None = None) -> dict[str, str]:
    envs = {
        key: value
        for key, value in os.environ.items()
        if value and any(key.startswith(prefix) for prefix in _ENV_PREFIXES)
    }
    envs.setdefault("OTEL_SDK_DISABLED", "true")
    envs.setdefault("VEADK_DISABLE_EXPIRE_AT", "true")
    envs.setdefault("ENABLE_APMPLUS", "false")
    envs.setdefault("ENABLE_COZELOOP", "false")
    for key, value in (extra_envs or {}).items():
        envs[key] = value
    return envs


def runtime_update_config(runtime_id: str, region: str) -> dict[str, Any]:
    runtime = get_runtime(runtime_id, region)
    version = int(getattr(runtime, "current_version_number", 0) or 0) + 1
    return {
        "runtime_id": runtime_id,
        "runtime_name": getattr(runtime, "name", "") or runtime_id,
        "runtime_role_name": getattr(runtime, "role_name", "") or "Auto",
        "image_tag": f"veadk-v{version}",
    }


def runtime_version(runtime_id: str, region: str) -> int | None:
    try:
        return getattr(get_runtime(runtime_id, region), "current_version_number", None)
    except Exception:
        return None


def get_runtime(runtime_id: str, region: str) -> Any:
    from agentkit.sdk.runtime import types as _rt
    from agentkit.sdk.runtime.client import AgentkitRuntimeClient

    ak, sk, token = resolve_ve_credentials()
    client = AgentkitRuntimeClient(
        access_key=ak,
        secret_key=sk,
        session_token=token,
        region=region,
    )
    return client.get_runtime(_rt.GetRuntimeRequest(runtime_id=runtime_id))


def resolve_ve_credentials() -> tuple[str, str, str]:
    access_key = os.getenv("VOLCENGINE_ACCESS_KEY", "")
    secret_key = os.getenv("VOLCENGINE_SECRET_KEY", "")
    session_token = os.getenv("VOLCENGINE_SESSION_TOKEN") or os.getenv(
        "VOLC_SESSIONTOKEN",
        "",
    )
    if not access_key or not secret_key:
        raise StudioAgentkitDeployError(
            "Volcengine credentials required: set VOLCENGINE_ACCESS_KEY/"
            "VOLCENGINE_SECRET_KEY for AgentKit Runtime deployment."
        )
    return access_key, secret_key, session_token


def tos_bucket_name(region: str) -> str:
    region_suffix = region.split("-")[-1]
    try:
        from agentkit.utils.template_utils import render_template

        bucket_base = render_template("agentkit-platform-{{account_id}}")
    except Exception:
        bucket_base = "agentkit-platform"
    return f"{bucket_base}-{region_suffix}"


def result_error_text(result: Any) -> str:
    parts: list[str] = []
    for obj in (
        result,
        getattr(result, "build_result", None),
        getattr(result, "deploy_result", None),
    ):
        if obj is None:
            continue
        for attr in ("error", "error_code"):
            value = getattr(obj, attr, None)
            if value:
                parts.append(str(value))
    return "\n".join(parts)


class ProgressReporter:
    """AgentKit reporter that forwards SDK messages into a simple callback."""

    def __init__(self, progress: Callable[[str], None]) -> None:
        from agentkit.toolkit.reporter import Reporter

        class _Reporter(Reporter):
            def info(self, message: object, **_kwargs: Any) -> None:
                progress(str(message))

            def success(self, message: object, **_kwargs: Any) -> None:
                progress(str(message))

            def warning(self, message: object, **_kwargs: Any) -> None:
                progress(str(message))

            def error(self, message: object, **_kwargs: Any) -> None:
                progress(str(message))

            def progress(
                self, message: object, current: int, total: int = 100, **_kwargs: Any
            ) -> None:
                progress(str(message))

            def confirm(
                self, message: object, default: bool = False, **_kwargs: Any
            ) -> bool:
                return default

            @contextmanager
            def long_task(self, description: object, total: int = 100):
                progress(str(description))

                class _Handle:
                    def update(
                        self,
                        description: object | None = None,
                        completed: int | None = None,
                    ) -> None:
                        if description:
                            progress(str(description))

                yield _Handle()

            def show_logs(
                self, title: object, lines: Iterable[object], max_lines: int = 100
            ) -> None:
                progress(str(title))

        self._reporter = _Reporter()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._reporter, name)


def _write_project(project: dict[str, Any], base: Path) -> None:
    for item in project["files"]:
        path = Path(item["path"])
        full = (base / path).resolve()
        if not full.is_relative_to(base):
            raise StudioAgentkitDeployError(f"Illegal file path: {item['path']}")
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(item["content"], encoding="utf-8")
    if not (base / "app.py").exists():
        raise StudioAgentkitDeployError("AgentProject must contain app.py")


def _created_runtime_id(created: Any) -> str:
    return str(
        getattr(created, "runtime_id", "")
        or getattr(getattr(created, "agent_kit_runtime", None), "runtime_id", "")
        or ""
    )


def _emit(progress: Callable[[str], None] | None, message: str) -> None:
    if progress is not None:
        progress(message)
