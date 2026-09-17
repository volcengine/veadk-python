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

"""Progress for the scheduler's standalone Function deployments."""

from __future__ import annotations

from threading import Event, Thread
from types import TracebackType
from typing import Any

from veadk.integrations.ve_faas.release_progress import (
    ReleaseProgress,
    redact_release_log,
)
from veadk.utils.logger import get_logger

from .diagnostics import sanitize_diagnostic

logger = get_logger(__name__)
_HEARTBEAT_INTERVAL_SECONDS = 15


class FunctionDeploymentProgress(ReleaseProgress):
    def __init__(self, service: Any, name: str, *, worker: bool = False) -> None:
        provider = getattr(service, "provider", "volcengine")
        self.region = getattr(service, "region", "")
        label = (
            ("Worker" if worker else "Scanner")
            if provider == "byteplus"
            else ("任务执行器" if worker else "定时扫描器")
        )
        secrets = tuple(
            str(getattr(service, key, "") or "")
            for key in ("ak", "sk", "session_token")
        )
        super().__init__(
            provider=provider,
            region=self.region,
            app_id=name,
            resource_label="Function",
            secrets=secrets,
            emit=lambda message: logger.info(
                "[%s] %s", label, sanitize_diagnostic(message, secrets=secrets)
            ),
        )
        self._stop = Event()
        self._heartbeat = Thread(
            target=self._keep_waiting, name="studio-function-progress", daemon=True
        )

    def __enter__(self) -> FunctionDeploymentProgress:
        self._heartbeat.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._stop.set()
        self._heartbeat.join()
        if exc_type is not None:
            self.message(
                self.text("部署未完成", "Deployment did not complete")
                + f" | {self.stage} | {self.text('已用时', 'Elapsed')} {self.elapsed()}"
            )

    def _keep_waiting(self) -> None:
        # No network calls here: even a blocking SDK mutation needs a heartbeat.
        while not self._stop.wait(min(1, _HEARTBEAT_INTERVAL_SECONDS)):
            self.waiting(_HEARTBEAT_INTERVAL_SECONDS)

    def step(self, chinese: str, english: str) -> None:
        self.status(self.text(chinese, english), None)

    def function(self, function_id: str) -> None:
        host = "console.byteplus.com" if self.english else "console.volcengine.com"
        self.message(
            f"Function ID: {function_id} | "
            f"https://{host}/vefaas/region:vefaas+{self.region}/function/detail/{function_id}"
        )

    def release_status(self, response: Any) -> None:
        state = str(getattr(response, "status", "") or "Unknown")
        revision = getattr(response, "new_revision_number", None)
        self.status(self.text("发布状态", "Release status") + f": {state}", revision)
        lines = [
            self.detail(getattr(response, field, ""))
            for field in ("status_message", "error_code", "failed_instance_logs")
            if getattr(response, field, None)
        ]
        # Function status responses contain snapshots, not Application log URLs.
        self._new_lines("release-status", lines, self.text("发布日志", "Release log"))

    def detail(self, value: Any) -> str:
        return sanitize_diagnostic(
            redact_release_log(str(value or ""), self.secrets),
            secrets=self.secrets,
            limit=2_000,
        )

    def log_error(self, *, final: bool = False) -> None:
        if not final:
            super().log_error()
            return
        self.warning(
            "final-dependency-log",
            self.text(
                "未能读取最终依赖安装日志，可在 Function 控制台查看",
                "Final dependency installation logs could not be read; check the Function console",
            ),
        )

    def ready(self, timer_id: str) -> None:
        self.message(
            self.text("部署完成，每分钟触发", "Deployment complete; runs every minute")
            + f" | Timer ID: {timer_id} | {self.text('总耗时', 'Total elapsed')} {self.elapsed()}"
        )
