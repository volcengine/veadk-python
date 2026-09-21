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

from threading import Event, enumerate as enumerate_threads
from types import SimpleNamespace
from typing import Any

import pytest

from frontend.service.studio_scheduler.deploy import (
    _extended_vefaas_request_timeout,
    _install_dependencies,
    _release_function,
)
from frontend.service.studio_scheduler.deploy_progress import FunctionDeploymentProgress


@pytest.fixture
def messages(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    lines: list[str] = []
    monkeypatch.setattr(
        "frontend.service.studio_scheduler.deploy_progress.logger.info",
        lambda message, *args: lines.append(message % args if args else message),
    )
    return lines


@pytest.fixture
def service() -> Any:
    return SimpleNamespace(
        provider="byteplus",
        region="ap-southeast-1",
        ak="private-access-key",
        sk="private-secret-key",
        session_token="private-session-token",
        client=SimpleNamespace(),
    )


@pytest.mark.parametrize("operation", ["install", "release"])
@pytest.mark.parametrize("error", [None, RuntimeError, KeyboardInterrupt])
def test_blocking_sdk_call_keeps_printing_and_stops_heartbeat(
    service: Any,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
    error: type[BaseException] | None,
) -> None:
    messages: list[str] = []
    waiting = Event()

    def emit(message: str, *args: Any) -> None:
        text = message % args if args else message
        messages.append(text)
        if "No new logs" in text:
            waiting.set()

    def blocking_request(_: Any) -> None:
        # The heartbeat must arrive before this synchronous SDK request returns.
        assert waiting.wait(2), "No progress while the SDK request is blocked"
        if error:
            raise error("interrupted request")

    monkeypatch.setattr(
        "frontend.service.studio_scheduler.deploy_progress.logger.info", emit
    )
    monkeypatch.setattr(
        "frontend.service.studio_scheduler.deploy_progress._HEARTBEAT_INTERVAL_SECONDS",
        0.01,
    )
    service.client.release = blocking_request
    service.client.create_dependency_install_task = blocking_request
    service.client.get_release_status = lambda _: SimpleNamespace(status="Success")
    service.client.get_dependency_install_task_status = lambda _: SimpleNamespace(
        status="Success"
    )
    before = set(enumerate_threads())

    def deploy() -> None:
        with FunctionDeploymentProgress(
            service, "test-worker", worker=True
        ) as progress:
            progress.function("fn-1")
            action = (
                _install_dependencies if operation == "install" else _release_function
            )
            action(service, "fn-1", progress)

    if error:
        with pytest.raises(error):
            deploy()
    else:
        deploy()
    assert waiting.is_set()
    assert not any(
        thread not in before and thread.name == "studio-function-progress"
        for thread in enumerate_threads()
    )
    heartbeat = next(message for message in messages if "No new logs" in message)
    assert "[Worker]" in heartbeat
    assert "Submitting" in heartbeat and "Elapsed" in heartbeat
    assert any("console.byteplus.com" in message for message in messages)


def test_release_failure_prints_status_and_sanitized_instance_logs(
    service: Any,
    messages: list[str],
) -> None:
    service.client.release = lambda _: None
    service.client.get_release_status = lambda _: SimpleNamespace(
        status="Failed",
        new_revision_number=3,
        error_code="StartFailed",
        status_message="Health check failed",
        failed_instance_logs="ImportError: missing_module private-secret-key token=private-token https://logs.example/x?signature=private-signature",
    )
    with pytest.raises(RuntimeError, match="ImportError: missing_module") as error:
        with FunctionDeploymentProgress(service, "worker", worker=True) as progress:
            _release_function(service, "fn-1", progress)
    output = "\n".join(messages) + str(error.value)
    for text in (
        "Health check failed",
        "StartFailed",
        "Revision: 3",
        "Deployment did not complete",
    ):
        assert text in output
    for secret in ("private-secret-key", "private-token", "private-signature"):
        assert secret not in output


def test_dependency_failure_retains_build_tail_and_redacts_secrets(
    service: Any,
    monkeypatch: pytest.MonkeyPatch,
    messages: list[str],
) -> None:
    service.client.create_dependency_install_task = lambda _: None
    service.client.get_dependency_install_task_status = lambda _: SimpleNamespace(
        status="Failed"
    )
    service.client.get_dependency_install_task_log_download_uri = lambda _: (
        SimpleNamespace(
            download_url="https://logs.example/download?signature=private-signature"
        )
    )
    monkeypatch.setattr(
        "veadk.integrations.ve_faas.release_progress._read_build_log",
        lambda _: (
            "No matching distribution found\nprivate-access-key password=private-password",
            False,
        ),
    )
    with pytest.raises(RuntimeError, match="No matching distribution found") as error:
        with FunctionDeploymentProgress(service, "scanner") as progress:
            _install_dependencies(service, "fn-1", progress)
    output = "\n".join(messages) + str(error.value)
    assert "[Build log] No matching distribution found" in output
    for secret in ("private-access-key", "private-password", "private-signature"):
        assert secret not in output


def test_optional_log_requests_use_short_timeout_and_do_not_abort_installation(
    service: Any,
    monkeypatch: pytest.MonkeyPatch,
    messages: list[str],
) -> None:
    states = iter(["Running", "Running", "Success"])
    timeouts: list[int] = []

    def unavailable(_: Any, **kwargs: Any) -> Any:
        timeouts.append(kwargs["_request_timeout"])
        raise TimeoutError("private-secret-key")

    service.client.create_dependency_install_task = lambda _: None
    service.client.get_dependency_install_task_status = lambda _: SimpleNamespace(
        status=next(states)
    )
    service.client.get_dependency_install_task_log_download_uri = unavailable
    monkeypatch.setattr(
        "frontend.service.studio_scheduler.deploy.time.sleep", lambda _: None
    )
    with _extended_vefaas_request_timeout(service):
        with FunctionDeploymentProgress(service, "scanner") as progress:
            _install_dependencies(service, "fn-1", progress)
    output = "\n".join(messages)
    assert timeouts == [5, 5, 5]
    assert output.count("Cloud logs are temporarily unavailable") == 1
    assert "success" in output
    assert "private-secret-key" not in output
    assert service.client.get_dependency_install_task_log_download_uri is unavailable
