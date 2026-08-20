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

"""Deploy the stateless cronjob scheduler beside Studio."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Any

from .diagnostics import sanitize_diagnostic

_TIMER_NAME = "veadk-studio-cronjobs-minute"
_MINUTE_CRONTAB = "* * * * *"


def scheduler_function_name(studio_application_name: str) -> str:
    """Return a deterministic VeFaaS-safe name kept below the service limit."""
    normalized = studio_application_name.strip().replace("_", "-")
    suffix = "-cronjobs"
    return f"{normalized[: 64 - len(suffix)].rstrip('-')}{suffix}"


def deploy_scheduler(
    service: Any,
    *,
    studio_application_name: str,
    package_root: Path,
    role_trn: str,
    environment: dict[str, str],
) -> tuple[str, str]:
    """Create/update the scheduler Function and its idempotent minute trigger."""
    function_name = scheduler_function_name(studio_application_name)
    with tempfile.TemporaryDirectory(prefix="studio_cronjob_scheduler_") as tmp:
        deployment_root = Path(tmp)
        _stage_package(package_root, deployment_root)
        function_id = _find_function_id(service, function_name)
        if function_id:
            service._replace_application_code_bundle(
                function_id=function_id,
                path=str(deployment_root),
                environment_overrides=environment,
            )
        else:
            function_id = _create_function(
                service,
                function_name=function_name,
                deployment_root=deployment_root,
                role_trn=role_trn,
                environment=environment,
            )
        _install_dependencies(service, function_id)
        _release_function(service, function_id)
        timer_id = _ensure_minute_timer(service, function_id)
    return function_id, timer_id


def deploy_scheduler_for_studio_update(
    service: Any,
    *,
    studio_function_id: str,
    package_root: Path,
    provider: str,
    project: str,
    environment_overrides: dict[str, str],
) -> tuple[str, str, str]:
    """Update the scheduler from the same bundle used by Studio self-update."""
    from volcenginesdkvefaas import GetFunctionRequest

    current_function = service.client.get_function(
        GetFunctionRequest(id=studio_function_id)
    )
    current_environment = {
        str(item.key): str(item.value)
        for item in (getattr(current_function, "envs", None) or [])
        if getattr(item, "key", None)
    }
    merged_environment = {**current_environment, **environment_overrides}
    storage_bucket = merged_environment.get("VEADK_STUDIO_TOS_BUCKET", "").strip()
    storage_region = merged_environment.get("VEADK_STUDIO_TOS_REGION", "").strip()
    if not storage_bucket or not storage_region:
        raise ValueError("Studio self-update could not resolve scheduler TOS storage")
    role_trn = str(getattr(current_function, "role", "") or "").strip()
    if not role_trn:
        raise ValueError(
            "Studio Function does not expose an IAM role for the scheduler"
        )
    scheduler_base = (
        merged_environment.get("VEADK_STUDIO_CRONJOB_SCHEDULER_BASE", "").strip()
        or str(getattr(current_function, "name", "") or "").strip()
    )
    if not scheduler_base:
        raise ValueError("Studio Function name is unavailable for scheduler deployment")
    function_id, timer_id = deploy_scheduler(
        service,
        studio_application_name=scheduler_base,
        package_root=package_root,
        role_trn=role_trn,
        environment={
            "CLOUD_PROVIDER": provider,
            "AGENTKIT_CLOUD_PROVIDER": provider,
            "VEADK_STUDIO_TOS_BUCKET": storage_bucket,
            "VEADK_STUDIO_TOS_REGION": storage_region,
            "VEADK_STUDIO_TOS_ENDPOINT": merged_environment.get(
                "VEADK_STUDIO_TOS_ENDPOINT", ""
            ),
            "VEADK_STUDIO_PROJECT": project,
        },
    )
    return function_id, timer_id, scheduler_base


def _stage_package(package_root: Path, destination: Path) -> None:
    requirements = package_root / "requirements.txt"
    if not requirements.is_file():
        raise ValueError("Studio scheduler package is missing requirements.txt")
    shutil.copy2(requirements, destination / requirements.name)
    for wheel in package_root.glob("*.whl"):
        shutil.copy2(wheel, destination / wheel.name)
    run_script = destination / "run.sh"
    run_script.write_text(
        "#!/bin/bash\n"
        "set -e\n"
        'ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"\n'
        'cd "$ROOT_DIR"\n'
        'if [ -d "output" ]; then cd ./output/; fi\n'
        "export PYTHONPATH=$PYTHONPATH:./site-packages\n"
        "exec python3 -m uvicorn "
        "frontend.service.studio_scheduler.http_app:app "
        '--host 0.0.0.0 --port "${_FAAS_RUNTIME_PORT:-8000}"\n',
        encoding="utf-8",
    )
    run_script.chmod(0o755)


def _create_function(
    service: Any,
    *,
    function_name: str,
    deployment_root: Path,
    role_trn: str,
    environment: dict[str, str],
) -> str:
    import veadk.config

    original_environment = dict(veadk.config.veadk_environments)
    original_role = os.environ.get("IAM_ROLE")
    try:
        veadk.config.veadk_environments.clear()
        veadk.config.veadk_environments.update(environment)
        os.environ["IAM_ROLE"] = role_trn
        _, function_id = service._create_function(
            function_name,
            str(deployment_root),
        )
        return str(function_id)
    finally:
        veadk.config.veadk_environments.clear()
        veadk.config.veadk_environments.update(original_environment)
        if original_role is None:
            os.environ.pop("IAM_ROLE", None)
        else:
            os.environ["IAM_ROLE"] = original_role


def _find_function_id(service: Any, function_name: str) -> str:
    from volcenginesdkvefaas import ListFunctionsRequest

    page_number = 1
    functions: list[Any] = []
    while True:
        response = service.client.list_functions(
            ListFunctionsRequest(page_number=page_number, page_size=100)
        )
        functions.extend(list(getattr(response, "items", []) or []))
        total = int(getattr(response, "total", 0) or 0)
        if page_number * 100 >= total:
            break
        page_number += 1
    matches = [
        item for item in functions if str(getattr(item, "name", "")) == function_name
    ]
    if len(matches) > 1:
        raise RuntimeError(f"Multiple VeFaaS functions are named {function_name}")
    return str(getattr(matches[0], "id", "") or "") if matches else ""


def _release_function(service: Any, function_id: str) -> None:
    from volcenginesdkvefaas import GetReleaseStatusRequest, ReleaseRequest

    service.client.release(ReleaseRequest(function_id=function_id, revision_number=0))
    for _ in range(120):
        response = service.client.get_release_status(
            GetReleaseStatusRequest(function_id=function_id)
        )
        state = str(getattr(response, "status", "") or "").lower()
        if "succ" in state or state == "done":
            return
        if "fail" in state or "error" in state:
            detail = sanitize_diagnostic(
                " ".join(
                    str(value or "").strip()
                    for value in (
                        getattr(response, "error_code", ""),
                        getattr(response, "status_message", ""),
                    )
                    if value
                ),
                limit=2_000,
            )
            suffix = f". {detail}" if detail else ""
            raise RuntimeError(f"Scheduler function release failed: {state}{suffix}")
        time.sleep(5)
    raise RuntimeError("Scheduler function release did not finish in 10 minutes")


def _install_dependencies(service: Any, function_id: str) -> None:
    from volcenginesdkvefaas import (
        CreateDependencyInstallTaskRequest,
        GetDependencyInstallTaskLogDownloadURIRequest,
        GetDependencyInstallTaskStatusRequest,
    )

    service.client.create_dependency_install_task(
        CreateDependencyInstallTaskRequest(function_id=function_id)
    )
    for _ in range(120):
        response = service.client.get_dependency_install_task_status(
            GetDependencyInstallTaskStatusRequest(function_id=function_id)
        )
        state = str(getattr(response, "status", "") or "").lower()
        if "succ" in state or state == "done":
            return
        if "fail" in state or "error" in state:
            detail = ""
            try:
                log_response = (
                    service.client.get_dependency_install_task_log_download_uri(
                        GetDependencyInstallTaskLogDownloadURIRequest(
                            function_id=function_id
                        )
                    )
                )
                download_url = str(
                    getattr(log_response, "download_url", "") or ""
                ).strip()
                if download_url:
                    with urllib.request.urlopen(download_url, timeout=30) as log_stream:
                        detail = sanitize_diagnostic(
                            log_stream.read().decode("utf-8", "replace"),
                            limit=2_000,
                        )
            except Exception:  # noqa: BLE001 - diagnostics must not mask failure
                detail = ""
            suffix = f". {detail}" if detail else ""
            raise RuntimeError(
                f"Scheduler dependency installation failed: {state}{suffix}"
            )
        time.sleep(5)
    raise RuntimeError("Scheduler dependency installation did not finish in 10 minutes")


def _ensure_minute_timer(service: Any, function_id: str) -> str:
    from volcenginesdkvefaas import (
        CreateTimerRequest,
        ListTriggersRequest,
        UpdateTimerRequest,
    )

    response = service.client.list_triggers(
        ListTriggersRequest(function_id=function_id)
    )
    triggers = list(getattr(response, "items", []) or [])
    matches = [
        item
        for item in triggers
        if str(getattr(item, "name", "")) == _TIMER_NAME
        and str(getattr(item, "type", "")).lower() == "timer"
    ]
    if len(matches) > 1:
        raise RuntimeError(f"Multiple VeFaaS timers are named {_TIMER_NAME}")
    common = {
        "function_id": function_id,
        "crontab": _MINUTE_CRONTAB,
        "description": "Wake the VeADK Studio cronjob dispatcher every minute",
        "enable_concurrency": True,
        "enabled": True,
        "payload": json.dumps({"source": "veadk-studio-cronjobs"}),
        "retries": 0,
    }
    if matches:
        timer_id = str(getattr(matches[0], "id", "") or "")
        service.client.update_timer(UpdateTimerRequest(id=timer_id, **common))
        return timer_id
    created = service.client.create_timer(
        CreateTimerRequest(name=_TIMER_NAME, **common)
    )
    return str(getattr(created, "id", "") or "")


__all__ = [
    "deploy_scheduler",
    "deploy_scheduler_for_studio_update",
    "scheduler_function_name",
]
