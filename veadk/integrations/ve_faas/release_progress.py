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

"""Customer-facing progress while VeFaaS builds and releases a code bundle."""

import re
import time
import urllib.request
from collections.abc import Callable

_BUILD_LOG_BYTES = 256 * 1024
_LOG_URL_PATTERN = re.compile(r"https://[^\s<>\]\"']+")


def extract_release_log_urls(text: str) -> list[str]:
    urls = []
    for match in _LOG_URL_PATTERN.finditer(text):
        url = match.group(0).rstrip(").,;")
        if ".log" in url and url not in urls:
            urls.append(url)
    return urls


def redact_release_log(text: str, secrets: tuple[str, ...]) -> str:
    for secret in secrets:
        if secret:
            text = text.replace(secret, "***")
    text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)
    text = re.sub(r"(?i)(\bbearer\s+)[a-z0-9._~+/=-]+", r"\1***", text)
    text = re.sub(
        r"(?i)((?:api[_-]?key|access[_-]?key|secret[_-]?key|client[_-]?secret|"
        r"session[_-]?token|security[_-]?token|token|password)[\"']?\s*[:=]\s*)"
        r"(?:[\"'][^\"']*[\"']|[^\s,;]+)",
        r"\1***",
        text,
    )
    return re.sub(r"(https?://[^\s?]+)\?[^\s]+", r"\1?[REDACTED]", text)


def _read_build_log(url: str) -> tuple[str, bool]:
    """Request a log tail and bound the response if the server ignores Range."""
    request = urllib.request.Request(
        url, headers={"Range": f"bytes=-{_BUILD_LOG_BYTES}"}
    )
    with urllib.request.urlopen(request, timeout=3) as response:
        data = response.read(_BUILD_LOG_BYTES + 1)
        content_range = response.headers.get("Content-Range", "")
        partial_start = content_range.startswith(
            "bytes "
        ) and not content_range.startswith("bytes 0-")
        truncated = len(data) > _BUILD_LOG_BYTES
        data = data[:_BUILD_LOG_BYTES]
        if partial_start:
            # The byte range may start inside a UTF-8 character or a log line.
            data = data.partition(b"\n")[2]
        return data.decode("utf-8", "replace"), truncated


class ReleaseProgress:
    def __init__(
        self,
        *,
        provider: str,
        region: str,
        app_id: str,
        secrets: tuple[str, ...],
        emit: Callable[[str], None],
        resource_label: str = "Application",
    ) -> None:
        self.english = provider == "byteplus"
        self.secrets = secrets
        self.emit = emit
        self.started = time.monotonic()
        self.last_output = self.started
        self.stage = self.text("提交云端发布", "Submitting cloud release")
        self.last_status = ""
        self.revision: int | None = None
        self.snapshots: dict[str, list[str]] = {}
        self.links: dict[str, str] = {}
        self.link_cursor = 0
        self.warnings: set[str] = set()
        self.message(
            self.text("开始云端构建与部署", "Starting cloud build and deployment")
            + f" | {provider} / {region} | {resource_label}: {app_id}"
        )

    def text(self, chinese: str, english: str) -> str:
        return english if self.english else chinese

    def elapsed(self) -> str:
        minutes, seconds = divmod(int(time.monotonic() - self.started), 60)
        return f"{minutes:02d}:{seconds:02d}"

    def message(self, text: str) -> None:
        self.emit(redact_release_log(text, self.secrets))
        self.last_output = time.monotonic()

    def status(self, status: str, revision: int | None) -> None:
        if revision is not None and revision != self.revision:
            self.revision = revision
            self.message(f"Revision: {revision}")
        if status == self.last_status:
            return
        self.last_status = status
        self.stage = {
            "create_success": self.text(
                "等待云端构建与部署", "Waiting for cloud build and deployment"
            ),
            "deploying": self.text("云端构建与部署", "Cloud build and deployment"),
            "deploy_success": self.text("发布完成", "Deployment complete"),
            "deploy_fail": self.text("发布失败", "Deployment failed"),
        }.get(status, status)
        self.message(
            f"{self.stage} | {self.text('已用时', 'Elapsed')} {self.elapsed()}"
        )

    def waiting(self, interval: float = 15) -> None:
        if time.monotonic() - self.last_output >= interval:
            self.message(
                f"{self.stage} | {self.text('已用时', 'Elapsed')} {self.elapsed()} | "
                + self.text(
                    "暂无新日志，仍在等待云端处理",
                    "No new logs; waiting for the cloud service",
                )
            )

    def warning(self, key: str, message: str) -> None:
        if key not in self.warnings:
            self.warnings.add(key)
            self.message(message)

    def log_error(self) -> None:
        self.warning(
            "control",
            self.text(
                "暂时无法读取云端日志，将重试读取；部署状态仍会持续更新",
                "Cloud logs are temporarily unavailable; retrying while continuing to check deployment status",
            ),
        )

    def _new_lines(self, key: str, lines: list[str], label: str) -> list[str]:
        if not lines:
            return []
        previous = [
            redact_release_log(line, self.secrets)
            for line in self.snapshots.get(key, [])
        ]
        comparable = [redact_release_log(line, self.secrets) for line in lines]
        if (
            len(comparable) < len(previous)
            and previous[: len(comparable)] == comparable
        ):
            return []
        overlap = min(len(previous), len(lines))
        while overlap and previous[-overlap:] != comparable[:overlap]:
            overlap -= 1
        self.snapshots[key] = lines
        for line in lines[overlap:]:
            self.message(f"[{label}] {line}")
        return lines[overlap:]

    def logs(self, lines: list[str], *, final: bool = False) -> None:
        self.warnings.discard("control")
        flattened = [line for item in lines for line in str(item).splitlines()]
        for url in extract_release_log_urls("\n".join(flattened)):
            # Signed URLs may be refreshed while referring to the same log object.
            key = url.partition("?")[0]
            self.links[key] = url
        while len(self.links) > 8:
            key = next(iter(self.links))
            del self.links[key]
            self.snapshots.pop(key, None)
        new_lines = self._new_lines(
            "control", flattened, self.text("发布日志", "Release log")
        )
        for line in new_lines:
            # Use the stage reported by VeFaaS, never estimate build percentages.
            match = re.search(
                r"\[function\]\[[^\]]+\]\[(install|build|deploy|start)\]", line
            )
            if match and not final:
                self.stage = {
                    "install": self.text("安装依赖", "Installing dependencies"),
                    "build": self.text("构建镜像", "Building image"),
                    "deploy": self.text("发布服务", "Deploying service"),
                    "start": self.text("启动服务", "Starting service"),
                }[match.group(1)]
        if not self.links:
            return
        keys = list(self.links)
        # Fetch one build log per poll to keep deployment status checks responsive.
        selected = keys if final else [keys[self.link_cursor % len(keys)]]
        self.link_cursor += 1
        for key in selected:
            self.build_log(self.links[key], final=final)

    def build_log(self, url: str, *, final: bool = False) -> str:
        """Read a known build log URL, including URLs without a .log suffix."""
        key = url.partition("?")[0]
        try:
            content, truncated = _read_build_log(url)
        except Exception:
            # Build logs can appear later than the control-plane link.
            self.warning(
                "final:" + key if final else key,
                self.text(
                    "未能读取最终构建日志，可在云控制台查看",
                    "Final build log could not be read; check the cloud console",
                )
                if final
                else self.text(
                    "构建日志暂不可用，将继续尝试读取",
                    "Build log is not available yet; it will be retried",
                ),
            )
            return ""
        self.warnings.discard(key)
        lines = content.splitlines()
        if lines and (truncated or (not final and not content.endswith("\n"))):
            lines.pop()
        self._new_lines(key, lines, self.text("构建日志", "Build log"))
        if truncated:
            self.warning(
                "truncated:" + key,
                self.text(
                    "构建日志超出单次读取范围，完整日志可在云控制台查看",
                    "Build log exceeds the read limit; view the full log in the cloud console",
                ),
            )
        return redact_release_log("\n".join(lines), self.secrets)

    def complete(self, url: str) -> None:
        self.message(
            f"{self.text('云端部署成功', 'Cloud deployment succeeded')} | "
            f"{self.text('总耗时', 'Total elapsed')} {self.elapsed()} | {url}"
        )
