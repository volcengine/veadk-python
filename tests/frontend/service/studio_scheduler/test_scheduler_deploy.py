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

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from frontend.service.studio_scheduler.deploy import (
    deploy_scheduler,
    deploy_scheduler_for_studio_update,
    scheduler_function_name,
    scheduler_worker_function_name,
)


class _Client:
    def __init__(self) -> None:
        self.created_timers: list[Any] = []
        self.created_worker: Any = None
        self.events: list[str] = []

    def list_functions(self, _request: Any) -> Any:
        return SimpleNamespace(items=[], total=0)

    def release(self, _request: Any) -> None:
        self.events.append("release")

    def get_release_status(self, _request: Any) -> Any:
        return SimpleNamespace(status="Success")

    def create_dependency_install_task(self, _request: Any) -> None:
        self.events.append("install")

    def get_dependency_install_task_status(self, _request: Any) -> Any:
        return SimpleNamespace(status="Success")

    def list_triggers(self, _request: Any) -> Any:
        return SimpleNamespace(items=[])

    def create_timer(self, request: Any) -> Any:
        self.created_timers.append(request)
        return SimpleNamespace(id=f"timer-{len(self.created_timers)}")

    def create_function(self, request: Any) -> Any:
        self.created_worker = request
        return SimpleNamespace(id="worker-function-1")


class _Service:
    def __init__(self) -> None:
        self.client = _Client()
        self.created_bundle: Path | None = None

    def _create_function(self, _name: str, path: str) -> tuple[str, str]:
        bundle = Path(path)
        assert (bundle / "requirements.txt").is_file()
        assert "studio_scheduler.http_app:app" in (bundle / "run.sh").read_text()
        self.created_bundle = bundle
        return _name, "function-1"

    def _upload_and_mount_code(self, function_id: str, path: str) -> None:
        assert function_id == "worker-function-1"
        assert Path(path, "run.sh").is_file()


def test_deploy_creates_separate_function_and_minute_timer(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text("veadk-python\n", encoding="utf-8")
    service = _Service()

    function_id, timer_id, worker_function_id, worker_timer_id = deploy_scheduler(
        service,
        studio_application_name="studio_test",
        package_root=tmp_path,
        role_trn="trn:iam::role/studio",
        environment={"VEADK_STUDIO_TOS_BUCKET": "studio"},
    )

    assert function_id == "function-1"
    assert timer_id == "timer-1"
    assert worker_function_id == "worker-function-1"
    assert worker_timer_id == "timer-2"
    scanner_timer, worker_timer = service.client.created_timers
    assert scanner_timer.function_id == "function-1"
    assert scanner_timer.crontab == "* * * * *"
    assert scanner_timer.enable_concurrency is False
    assert scanner_timer.payload == '{"source":"veadk-studio-cronjobs","phase":"scan"}'
    assert worker_timer.function_id == "worker-function-1"
    assert worker_timer.enable_concurrency is True
    assert (
        worker_timer.payload == '{"source":"veadk-studio-cronjobs","phase":"execute"}'
    )
    assert service.client.created_worker.request_timeout == 10800
    assert service.client.created_worker.max_concurrency == 1
    assert service.client.created_worker.async_task_config.enable_async_task is True
    assert service.client.created_worker.async_task_config.max_retry == 0
    assert service.client.events == ["install", "release", "install", "release"]


def test_scheduler_function_name_is_safe_and_bounded() -> None:
    name = scheduler_function_name("studio_" + "a" * 100)
    worker_name = scheduler_worker_function_name("studio_" + "a" * 100)

    assert "_" not in name
    assert name.endswith("-cronjobs")
    assert len(name) <= 64
    assert "_" not in worker_name
    assert worker_name.endswith("-cronjobs-worker")
    assert len(worker_name) <= 64


def test_self_update_reuses_studio_role_storage_and_stable_name(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, Any] = {}

    class _UpdateClient:
        def get_function(self, _request: Any) -> Any:
            return SimpleNamespace(
                name="studio-function",
                role="trn:iam::role/studio",
                envs=[
                    SimpleNamespace(
                        key="VEADK_STUDIO_TOS_BUCKET",
                        value="existing-bucket",
                    ),
                    SimpleNamespace(
                        key="VEADK_STUDIO_CRONJOB_SCHEDULER_BASE",
                        value="stable-studio-app",
                    ),
                ],
            )

    service = SimpleNamespace(client=_UpdateClient())

    def _deploy(service_arg: Any, **kwargs: Any) -> tuple[str, str, str, str]:
        captured["service"] = service_arg
        captured.update(kwargs)
        return (
            "scheduler-function",
            "scheduler-timer",
            "worker-function",
            "worker-timer",
        )

    monkeypatch.setattr(
        "frontend.service.studio_scheduler.deploy.deploy_scheduler",
        _deploy,
    )

    result = deploy_scheduler_for_studio_update(
        service,
        studio_function_id="studio-function-id",
        package_root=tmp_path,
        provider="byteplus",
        project="default",
        environment_overrides={
            "VEADK_STUDIO_TOS_REGION": "ap-southeast-1",
            "VEADK_STUDIO_TOS_ENDPOINT": "tos-ap-southeast-1.bytepluses.com",
        },
    )

    assert result == (
        "scheduler-function",
        "scheduler-timer",
        "worker-function",
        "worker-timer",
        "stable-studio-app",
    )
    assert captured["service"] is service
    assert captured["studio_application_name"] == "stable-studio-app"
    assert captured["role_trn"] == "trn:iam::role/studio"
    assert captured["environment"] == {
        "CLOUD_PROVIDER": "byteplus",
        "AGENTKIT_CLOUD_PROVIDER": "byteplus",
        "VEADK_STUDIO_TOS_BUCKET": "existing-bucket",
        "VEADK_STUDIO_TOS_REGION": "ap-southeast-1",
        "VEADK_STUDIO_TOS_ENDPOINT": "tos-ap-southeast-1.bytepluses.com",
        "VEADK_STUDIO_PROJECT": "default",
    }
